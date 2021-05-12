# -*- coding: utf-8 -*-
#
# Copyright (C) 2021, Sebastian Nagel.
#
# This file is part of the module 'gapiannotator' and is released under
# the MIT License: https://opensource.org/licenses/MIT
#
import os
import pathlib
import subprocess
import time
from datetime import datetime
import re
import io
import threading
import queue as Queue
from typing import List
import dateutil.parser

import pyexiv2
import jpegtran
import PIL.Image

import numpy as np

from . import ROOT
from .gui import WebGUIServer
from .helper import sqlitedb, dms_to_decimal, Settings, EventHandler, size_fmt
from .gapi import Gapi


class ImageLibrary:
    DEFAULT_SETTINGS = {
        "num_threads" : 4,
        "gapi_key" : '',
        "gapi_credentials" : '',
        "valid_credentials" : False,
        "whitelist" : '(jpg|JPG|jpeg|JPEG)$',
        "blacklist" : '^\.|/\.|\@eaDir',
        "vision_features" : Gapi.VISION_FEATURES,
        "reverse_geocoding" : True,
        "scan_existing" : False,
        "scan_new" : True,
        "hash_size" : 8,
        "rotate_images" : False,
        "replace_labels" : False,
        "always_hide_menu" : False,
        "translate": 'en',
        "is_synology" : False,
        "paths" : []
    }
    def __init__(self, db_file: str = os.path.join(ROOT,'annotator.db')):
        self.db_file = os.path.abspath(db_file)
        self.db = sqlitedb(self.db_file)
        self.log_queue = []
        self.gapi = None
        self.processingqueue = Queue.Queue()
        self.event = EventHandler()
        self.checkTable()
        self.settings = Settings(self.db, self.DEFAULT_SETTINGS)
        self.settings.set_settings_changed_listener(self.on_settings_changed)
        
    def init_gapi(self):
        if not self.gapi and self.settings.gapi_key and self.settings.gapi_credentials:
            try:
                self.gapi = Gapi(self.settings.gapi_key, 
                                 self.settings.gapi_credentials,
                                 db = self.db)
            except Exception as e:
                print(e)
        return type(self.gapi) != type(None)
        
    def log(self,message):
        logentry = (datetime.now().strftime("%d.%m.%Y %H:%M:%S"),message)
        self.log_queue.append(logentry)
        while len(self.log_queue) > 1000:
            self.log_queue.pop(0)
        print(message)
        self.event('log',logentry)
        
    def checkTable(self):
        self.db.execute("""CREATE TABLE IF NOT EXISTS files(
            id INTEGER PRIMARY KEY,
            filePath TEXT NOT NULL UNIQUE, 
            isAnnotated INT2 DEFAULT 0, 
            hasFaces INT2 DEFAULT 0, 
            hasUntaggedFaces INT2 DEFAULT 0, 
            hasIgnoredFaces INT2 DEFAULT 0,
            hash TEXT NOT NULL DEFAULT 0,
            addedTimesamp INTEGER DEFAULT (strftime('%s', 'now')),
            modifedTimesamp INTEGER DEFAULT (strftime('%s', 'now')),
            originalTimestamp INTEGER);""",True)
        self.db.execute("""CREATE TABLE IF NOT EXISTS similarity(
            id1 INTEGER NOT NULL,
            id2 INTEGER NOT NULL, 
            dist INTEGER,
            PRIMARY KEY(id1,id2));""",True)
    
    def on_settings_changed(self,changed_settings):
        if any([key in changed_settings for key in ['scan_new','blacklist','paths','whitelist']]):
            if self.settings['scan_new'] and len(self.settings['paths']) > 0:
                self.watch()
            else:
                self.unwatch()
        
        if 'num_threads' in changed_settings:
            self.spawn_threads(self.settings['num_threads'])
            
        if 'hash_size' in changed_settings:
            self.rehash(self.settings['hash_size'])
            
    def get_images(self,paths: List[str]):
        files = self.scan_for_files(paths)
        return [self.get_image(file_path) for file_path in files if os.path.exists(file_path)]
    
    def get_image(self,file_path: str):
        return _Image(self,file_path)
    
    def spawn_threads(self, num_threads: int = DEFAULT_SETTINGS['num_threads']):
        if not hasattr(self,'processingthreads'):
            self.processingthreads = []
            
        if num_threads != len(self.processingthreads):
            self.log(f'Spawning {num_threads} annotation threads')
            
        # add threads if required
        for i in range(len(self.processingthreads),num_threads):
            t=ProcessingThread(self,self.processingqueue)
            t.start()
            self.processingthreads.append(t)
        
        # terminate threads if required
        [thread.terminate() for thread in self.processingthreads[num_threads:]]
    
    def build_filter(self,
                     whitelist: str=DEFAULT_SETTINGS['whitelist'],
                     blacklist: str=DEFAULT_SETTINGS['blacklist']):
        blacklist = re.compile(blacklist) if blacklist != None else None;
        whitelist = re.compile(whitelist) if whitelist != None else None;
        def filter(name, parent, is_dir):
            # blacklist first
            if blacklist != None and blacklist.search(name) != None:
                return False
            # whitelist only for files
            if whitelist != None and not is_dir:
                return whitelist.search(name) != None
            return True
        return filter
    
    def scan_for_files(self,
                       paths: List[str],
                       whitelist: str=DEFAULT_SETTINGS['whitelist'],
                       blacklist: str=DEFAULT_SETTINGS['blacklist']):
        filter = self.build_filter(whitelist,blacklist)
        # split files and folders
        folders = [os.path.abspath(path) for path in paths if os.path.isdir(path) and filter(os.path.abspath(path),None,os.path.isdir(path))]
        files = [os.path.abspath(path) for path in paths if os.path.isfile(path) and filter(os.path.abspath(path),None,os.path.isdir(path))]
        [files.extend([os.path.join(path, name) for path, subdirs, files in os.walk(path) for name in files if filter(os.path.join(path, name),None,os.path.isdir(os.path.join(path, name)))]) for path in folders]
        return files
    
    def process(self,
                 paths: List[str],
                 vision_features: dict = DEFAULT_SETTINGS['vision_features'],
                 reverse_geocoding: dict = DEFAULT_SETTINGS['reverse_geocoding'],
                 whitelist: str = DEFAULT_SETTINGS['whitelist'],
                 blacklist: str = DEFAULT_SETTINGS['blacklist'],
                 translate: str = DEFAULT_SETTINGS['translate'],
                 replace_labels: bool=DEFAULT_SETTINGS['replace_labels'],
                 rotate_images: bool=DEFAULT_SETTINGS['rotate_images'],
                 reannotate: bool = False,
                 blocking: bool = False):
        if not self.init_gapi():
            self.log('No valid GAPI key/credentials, skipping annotation.')
            return
        files = self.scan_for_files(paths,whitelist,blacklist)
        if files:
            # populate queue
            self.event('remaining_files',self.files_in_queue+len(files))
            [self.processingqueue.put({'file_path':file_path,
                                      'cmd': 'process',
                                      'vision_features':vision_features,
                                      'reverse_geocoding':reverse_geocoding,
                                      'translate':translate,
                                      'replace_labels':replace_labels,
                                      'rotate_images':rotate_images,
                                      'reannotate':reannotate}) for file_path in files]
            self.event('remaining_files',self.files_in_queue)
            if blocking:
                self.log('Processing {} file(s)...'.format(len(files)))
                while self.files_in_queue > 0:
                    print('Progress [{:.2f}%]\r'.format((1-(self.files_in_queue/len(files)))*100), end="")
                    time.sleep(0.5)
                self.processingqueue.join()
                self.log('Progress [100.00%]')
        else:
            self.log('No images found.')
            
    def rehash(self,hash_size: int=DEFAULT_SETTINGS['hash_size']):
        res = self.db.execute("SELECT filePath FROM files ORDER BY id ASC;").fetchall()
        self.db.execute("DELETE FROM similarity;",True) #TODO
        [self.processingqueue.put({'file_path':file_path, 'cmd': 'rehash', 'hash_size': hash_size}) for (file_path,) in res]
        
                
    def on_startup(self):
        self.spawn_threads(self.settings.num_threads)
        
        if self.settings.scan_existing:
            self.process(paths = self.settings.paths,
                          vision_features = self.settings.vision_features,
                          reverse_geocoding = self.settings.reverse_geocoding,
                          whitelist = self.settings.whitelist,
                          blacklist = self.settings.blacklist,
                          translate = self.settings.translate,
                          replace_labels = self.settings.replace_labels,
                          rotate_images = self.settings.rotate_images,
                          reannotate = False,
                          blocking = False)
            
        if self.settings.scan_new:
            self.watch()
    
    def launch_webinterface(self,
                            addr: str='0.0.0.0',
                            port: int=8000,
                            blocking: bool=False):
        if not hasattr(self,'webserver'):
            self.webserver = WebGUIServer(self,addr=addr,port=port)
            self.webserver.start()
            self.on_startup()
            if blocking:
                self.webserver.join()
                
    def move(self,from_path: str,to_path: str):
        esc_from_path = from_path.replace("'", "''")
        esc_to_path = to_path.replace("'", "''")
        is_dir = os.path.isdir(to_path)
        is_file = os.path.isfile(to_path)
        if is_dir:
            self.db.execute(f"UPDATE files SET filePath = REPLACE(filePath,'{esc_from_path}','{esc_to_path}');",True)
            self.log(f'Moved folder from {from_path} to {to_path}')
        elif is_file:
            filter = self.build_filter(self.settings.whitelist,self.settings.blacklist)
            if filter(from_path,None,False) and filter(to_path,None,False):
                self.db.execute(f"UPDATE files SET filePath = REPLACE(filePath,'{esc_from_path}','{esc_to_path}') WHERE filePath = '{esc_from_path}';",True)
                #TODO send websocket info
                self.log(f'Moved file from {from_path} to {to_path}')
                
    def delete(self,path: str,withdelay: bool=True):
        def remove_from_db():
            if not os.path.exists(path):
                if self.settings.is_synology:
                    subprocess.run(['/usr/syno/bin/synoindex', '-d', path],capture_output=True)

                esc_path = path.replace("'", "''")
                try:
                    (imgindex,)=self.db.execute(f"SELECT id FROM files WHERE filePath = '{esc_path}';").fetchone()
                    self.event('deleted_image',imgindex)
                    self.log(f'Removed file {path}') 
                    self.db.execute(f"DELETE FROM files WHERE id = {imgindex};",True)
                    self.db.execute(f"DELETE FROM similarity WHERE id1 = {imgindex} OR id2 = {imgindex};",True) 
                except:
                    pass
                
        filter = self.build_filter(self.settings.whitelist,self.settings.blacklist)
        if filter(path,None,False):
            # we delete with an delay of 10 seconds because jpegtran does not modify, but delete and write a new file
            if withdelay:
                threading.Timer(10,remove_from_db).start()
            else:
                remove_from_db()
    
    def clean(self):
        deleted_files = tuple([file_id for (file_id, file_path) in self.db.execute("SELECT id,filePath FROM files;").fetchall() if not os.path.exists(file_path)])
        self.db.execute(f"DELETE FROM files WHERE id IN {deleted_files};",True)
        self.log(f'Cleared {len(deleted_files)} file(s)')
        
    def unwatch(self):
        if hasattr(self,'watch_thread'):
            self.watch_thread.terminate()
            
    def watch(self):
        self.unwatch()
        self.watch_thread = WatchFolderThread(self)
        self.watch_thread.start()
        
    @property
    def files_in_queue(self):
        return self.processingqueue.qsize()

class WatchFolderThread(threading.Thread):
    def __init__(self,library):
        threading.Thread.__init__(self)
        self.daemon = True
        
        self.library = library
        self._terminate = False
        
        from inotifyrecursive import INotify, flags
        self.inotify = INotify()
        self.watch_flags = flags.CREATE | flags.MODIFY | flags.MOVED_TO | flags.MOVED_FROM | flags.DELETE | flags.CLOSE_WRITE
        
    def add_paths(self,paths):
        filter = self.library.build_filter(self.library.settings.whitelist,self.library.settings.blacklist)
        folders = [path for path in paths if os.path.isdir(path)]
        if not folders:
            return False
        self.library.log("Adding paths to watchlist, this may take some time...")
        [self.inotify.add_watch_recursive(path, self.watch_flags, filter) for path in folders]
        return True
        
    def terminate(self):
        self._terminate = True
        
    def run(self):
        from inotifyrecursive import flags
        if not self.add_paths(self.library.settings.paths):
            self.library.log('No folders to watch...skipping')
            return
        new_files = set()
        modified_files = set()
        moved_from = {}
        
        self.library.log("Waiting for file changes...")
        while True:
            for event in self.inotify.read(timeout=100):
                is_dir = event.mask & flags.ISDIR
                fullpath = os.path.join(self.inotify.get_path(event.wd), event.name)
                if event.mask & flags.CREATE:
                    if is_dir:
                        pass # new folder event can be ignored, because an event is fired for each file
                    else:
                        new_files.add(fullpath) # we will wait until file is written (see flags.CLOSE_WRITE)
                if event.mask & flags.MODIFY:
                    if is_dir:
                        pass # modified folder event, will this happen?
                    else:
                        modified_files.add(fullpath) # we will wait until file is written (see flags.CLOSE_WRITE)
                elif event.mask & flags.MOVED_TO:
                    if event.cookie and str(event.cookie) in moved_from:
                        frompath = moved_from[str(event.cookie)]
                        self.library.move(frompath,fullpath)
                        del moved_from[str(event.cookie)]
                    else:
                        pass #TODO does this case ever happen?
                elif event.mask & flags.DELETE or event.mask & flags.MOVED_FROM:
                    if event.cookie:
                        moved_from[str(event.cookie)] = fullpath
                    else:
                        if is_dir:
                            pass # delete folder event can be ignored, because an event is fired for each file
                        else:
                            self.library.delete(fullpath)
                elif event.mask & flags.CLOSE_WRITE:
                    if (fullpath in new_files):
                        new_files.remove(fullpath)
                        if (fullpath in modified_files):
                            modified_files.remove(fullpath)
                        self.library.process(paths = [fullpath],
                                              vision_features = self.library.settings.vision_features,
                                              reverse_geocoding = self.library.settings.reverse_geocoding,
                                              whitelist = self.library.settings.whitelist,
                                              blacklist = self.library.settings.blacklist,
                                              translate = self.library.settings.translate,
                                              replace_labels = self.library.settings.replace_labels,
                                              rotate_images = self.library.settings.rotate_images,
                                              reannotate = False,
                                              blocking = False)
                    elif (fullpath in modified_files):
                        modified_files.remove(fullpath)
                        #queue.put(fullpath) #TODO maybe as option flag
            if (self._terminate):
                break;
        self.library.log("Stop watching.")
        
class ProcessingThread(threading.Thread):
    def __init__(self,
                 library: ImageLibrary,
                 queue: Queue.Queue):
        threading.Thread.__init__(self)
        self.daemon = True
        
        self.library = library
        self.queue=queue
        self._terminate=False
        
    def terminate(self):
        # note: threads will be terminated AFTER its next annotation process
        self._terminate = True

    def run(self):
        while True:
            args=self.queue.get()
            try:
                file_path = args.pop('file_path')
                cmd = args.pop('cmd')
                image = _Image(self.library,file_path)
                getattr(image,cmd)(**args)
                image.save()
            except Exception as e:
                self.library.log(f'Error while calling "{cmd}" on file {file_path}\nError message: {e}')
            self.library.event('remaining_files',self.queue.qsize())
            self.queue.task_done()
            if (self._terminate):
                break

class _Image:
    THUMBNAILS = {'S': {'size':(160,160),'file_name':'SYNOPHOTO_THUMB_S.jpg','quality':90,'crop':False},
                  'M': {'size':(320,320),'file_name':'SYNOPHOTO_THUMB_M.jpg','quality':90,'crop':False},
                  'B': {'size':(640,640),'file_name':'SYNOPHOTO_THUMB_B.jpg','quality':90,'crop':False},
                  'L': {'size':(800,800),'file_name':'SYNOPHOTO_THUMB_L.jpg','quality':90,'crop':False},
                  'XL':{'size':(1280,1280),'file_name':'SYNOPHOTO_THUMB_XL.jpg','quality':90,'crop':False},
                  'P': {'size':(120,160),'file_name':'SYNOPHOTO_THUMB_PREVIEW.jpg','quality':90,'crop':True}}

    def __init__(self,
                 library: ImageLibrary,
                 file_path: str):
        self.library = library
        self.file_path = os.path.abspath(file_path)
        self.file = pathlib.Path(self.file_path)
        self._thumbnails = {}
        self.path = self.file.parent
        self.file_name = self.file.name
        self.changed = False
        self.is_new_file = False
        self.index # reads/creates an unique index
        
    @property
    def exists(self):
        return self.file.exists()
    
    @property
    def file_size(self):
        if self.file.exists():
            return self.file.stat().st_size
        return 0
    
    @property
    def file_size_readable(self):
        return size_fmt(self.file_size)
    
    @property
    def hash(self):
        if not hasattr(self,'_hash'):
            self.rehash(self.library.settings.hash_size)
        return self._hash
    
    def rehash(self,hash_size: int=ImageLibrary.DEFAULT_SETTINGS['hash_size']):
        if not hasattr(self,'_hash'):
            (self._hash, ) = self.library.db.execute(f"SELECT hash FROM files WHERE id = {self.index};").fetchone()
        if not self._hash or not (len(self._hash) == int(np.ceil((hash_size**2)/4))):
            #image = PIL.Image.open(io.BytesIO(self.get_thumbnail('S').as_blob()))
            image = PIL.Image.open(self.create_thumbnail('S'))
            image = image.convert("L").resize((hash_size + 1, hash_size), PIL.Image.ANTIALIAS)
            pixels = np.asarray(image)
            # compute dhash
            binhash = pixels[:, 1:] > pixels[:, :-1]
            bit_string = ''.join(str(b) for b in 1 * binhash.flatten())
            width = int(np.ceil(len(bit_string)/4))
            self._hash = '{:0>{width}x}'.format(int(bit_string, 2), width=width)
            
            maxdist = int(round(width*4*0.1))
            # calculate distances between all images in SQL (fast)
            if self.library.db.hexhammdist:
                self.library.db.execute(f"INSERT INTO similarity (id1, id2, dist) SELECT id, {self.index} AS id2, hexhammdist(hash, '{self._hash}') as hd FROM files WHERE id < {self.index} AND length(hash)={width} AND hd <= {maxdist};", True)
                #values = self.library.db.execute(f"SELECT a.id, b.id, hexhammdist(a.hash, b.hash) FROM files a INNER JOIN files b ON b.id = {self.index} AND a.id < b.id AND length(a.hash)=length(b.hash);").fetchall()
                #values = ", ".join([f'({id1}, {id2}, {dist})' for (id1,id2,dist) in values])
                #self.library.db.execute(f"INSERT INTO similarity (id1, id2, dist) VALUES {values}",True)
            # calculate distances between all images in python (slow)
            else:
                res = self.library.db.execute(f"SELECT id, hash FROM files FROM files WHERE id < {self.index} AND length(hash)={width};").fetchall()
                values = []
                for (idx,hash1) in res:
                    hash1 = [int(x) for x in bin(int(hash1, 16))[2:].zfill(len(hash1)*4)]
                    hash2 = [int(x) for x in bin(int(self._hash, 16))[2:].zfill(len(self._hash)*4)]
                    dist = np.count_nonzero(np.array(hash1)!=np.array(hash2))
                    if dist <= maxdist:
                        values.append((idx,self.index,dist))
            
                if values:
                    values = ", ".join([f'({id1}, {id2}, {dist})' for (id1,id2,dist) in values])
                    self.library.db.execute(f"INSERT INTO similarity (id1, id2, dist) VALUES {values}",True)
    
    def __hash__(self):
        return self.hash
    
    def __str__(self):
        return self.hash

    def __sub__(self, other):
        binhash1 = [int(x) for x in bin(int(self.hash, 16))[2:].zfill(len(self.hash)*4)]
        binhash2 = [int(x) for x in bin(int(other.hash, 16))[2:].zfill(len(other.hash)*4)]
        return np.count_nonzero(np.array(binhash1) != np.array(binhash2))

    def __eq__(self, other):
        if other is None:
            return False
        return self.hash == other.hash

    def __ne__(self, other):
        if other is None:
            return False
        return not self.hash == other.hash
    
    @property
    def date(self):
        if not hasattr(self,'_date'):
            (self._date, ) = self.library.db.execute(f"SELECT originalTimestamp FROM files WHERE id = {self.index};").fetchone()
            if (not self._date): # or not 'Exif.Photo.DateTimeOriginal' in self.metadata): #TODO
                try:
                    # use exif tag
                    self._date = self.metadata['Exif.Photo.DateTimeOriginal'].value.timestamp()
                except:
                    try:
                        # search filename
                        # remove possible numbers at the end of the file name (causes problems for dateutil parser)
                        timestring = re.sub(r"[^\d]\d{1,5}\..{3,4}$",'',self.file_name)
                        self._date = dateutil.parser.parse(timestring,fuzzy=True).timestamp()
                    except:
                        # use file modification date
                        self._date = self.file.stat().st_mtime
        return self._date
    
    @property
    def index(self):
        if not hasattr(self,'_index'):
            esc_file_path = self.file_path.replace("'", "''")
            try:
                (self._index, ) = self.library.db.execute(f"SELECT id FROM files WHERE filePath = '{esc_file_path}';").fetchone()
            except TypeError:
                self.is_new_file = True
                self.library.db.execute(f"INSERT INTO files (filePath) VALUES ('{esc_file_path}');",True)
                return self.index
        return int(self._index)
    
    @property
    def is_annotated(self):
        if not hasattr(self, '_is_annotated'):
            (self._is_annotated, ) = self.library.db.execute(f"SELECT isAnnotated FROM files WHERE id = {self.index};").fetchone()
        return bool(int(self._is_annotated))
    
    @is_annotated.setter
    def is_annotated(self,value: bool):
         self._is_annotated = value
         self.changed = True
    
    def update_db_entry(self,updateTimestamp:bool=True):
        isAnnotated = int(self.is_annotated)
        hasFaces = int(bool(self.faces))
        hasUntaggedFaces = int(bool(self.untagged_faces))
        hasIgnoredFaces = int(bool(self.ignored_faces))
        
        modifedTimesamp = ""
        if updateTimestamp:
            timestamp = int(time.time())
            modifedTimesamp = f", modifedTimesamp = {timestamp}"
        
        self.library.db.execute(f"""UPDATE files
                            SET isAnnotated = {isAnnotated},
                                hasFaces = {hasFaces},
                                hasUntaggedFaces = {hasUntaggedFaces},
                                hasIgnoredFaces = {hasIgnoredFaces},
                                hash = '{self.hash}',
                                originalTimestamp = {self.date}
                                {modifedTimesamp}
                            WHERE
                                id = {self.index};""",True)
            
    @property 
    def thumb_path(self):
        if self.library.settings.is_synology:
            return os.path.join(self.path,'@eaDir',self.file_name)
        else:
            return os.path.join(self.path,'.thumbs',self.file_name)
        
    def remove_exif_orientation(self):
        if self.orientation != 1:
            jpegtran.JPEGImage(self.file_path).exif_autotransform().save(self.file_path)
            
            # force reread of metadata
            delattr(self,'_metadata')
        
    def get_downscale_size(self,x:int,y:int,new_x:int,new_y:int,use_max:bool=True):
        if use_max:
            scale = max(x/new_x,y/new_y)
        else:
            scale = min(x/new_x,y/new_y)
        if scale > 1:
            return (int(round(x/scale)),int(round(y/scale)))
        else:
            return (x,y)
        
    def create_all_thumbnails(self):
        for size in self.THUMBNAILS.keys():
            self.create_thumbnail(size)
    
    def create_thumbnail(self,size: str='L'):
        if not size in self.THUMBNAILS:
            size = 'L'
        prop = self.THUMBNAILS[size]
        thumb_file = os.path.abspath(os.path.join(self.thumb_path,prop['file_name']))
        
        if not os.path.exists(thumb_file):
            img = jpegtran.JPEGImage(self.file_path)
            if self.orientation !=1:
                img=img.exif_autotransform()
            
            os.makedirs(self.thumb_path, exist_ok=True)
        
            if not prop['crop']:
                img.downscale(*self.get_downscale_size(img.width,img.height,*prop['size']),prop['quality']
                              ).save(thumb_file)
            else:
                (x,y) = prop['size']
                img = img.downscale(*self.get_downscale_size(img.width,img.height,x,y,False),prop['quality'])
                (offset_x,offset_y) = (int(round((img.width-x)/2)),int(round((img.height-y)/2)))
                # jpeg lossless cropping requires (at worst) a multiple of 16x16 pixels
                (offset_x,offset_y) = (offset_x-(offset_x % 16),offset_y-(offset_y % 16))
                img.crop(offset_x,offset_y,x,y).save(thumb_file)
                    
        return thumb_file
        
    @property
    def orientation(self):
        orientation = 1
        if 'Exif.Image.Orientation' in self.metadata:
            orientation = self.metadata['Exif.Image.Orientation'].value
        return orientation
        
    def save(self,force_db_update: bool=True):
        if self.changed:
            self.clean_metadata()
            self.metadata.write(preserve_timestamps=True)
            self.update_db_entry()
            if self.library.settings.is_synology:
                output = subprocess.run(['/usr/syno/bin/synoindex', '-a', self.file_path],capture_output=True)
                if output.returncode != 0:
                    self.library.log(f'Warning: failed to reindex file {self.file_path}')
            if self.is_new_file:
                self.library.event('new_image',self)
        elif force_db_update:
            self.update_db_entry(updateTimestamp=False)
        
    def clean_metadata(self):
        # remove lightroom hierarchical labels
        self.metadata.pop('Xmp.lr.hierarchicalSubject',None)
        self.changed = True
    
    @property
    def labels(self):
        if 'Xmp.dc.subject' in self.metadata:
            return self.metadata['Xmp.dc.subject'].value
        else:
            return []
    
    @labels.setter
    def labels(self,value: List[str]):
        if (not type(value) == type(None)):
            key = 'Xmp.dc.subject'
            self.metadata[key] = pyexiv2.xmp.XmpTag(key, list(set(value)))
            self.changed = True
    
    def get_thumbnail(self,size:str='L'):
        if not size in self._thumbnails:
            self._thumbnails[size] = jpegtran.JPEGImage(self.create_thumbnail(size))
        return self._thumbnails[size]
    
    def add_face(self,rect:List[float],name:str=''):
        face = self._Face(self,len(self.faces)+1,name,rect)
        self._faces.append(face)
        
    @property
    def untagged_faces(self):
        return [face for face in self.faces if face.name == '' and not face.ignored]
        
    @property
    def ignored_faces(self):
        return [face for face in self.faces if face.ignored]
        
    @property
    def named_faces(self):
        return [face for face in self.faces if not face.name == '']
    
    @property
    def faces(self):
        if not hasattr(self,'_faces'):
            self._faces = []
            faceidx = 1
            while 'Xmp.MP.RegionInfo/MPRI:Regions[{}]/MPReg:Rectangle'.format(faceidx) in self.metadata:
                self._faces.append(self._Face(self, faceidx))
                faceidx += 1
        return self._faces
    
    def clear_faces(self):
        [face.delete() for face in self.faces]
        delattr(self, '_faces')
    
    @property
    def metadata(self):
        if not hasattr(self,'_metadata'):
            self._metadata = pyexiv2.ImageMetadata(self.file_path)
            self._metadata.read()
        return self._metadata
    
    @property
    def latlon(self):
        if not hasattr(self,'_latlon'):
            try:
                self._latlon = (dms_to_decimal(self.metadata['Exif.GPSInfo.GPSLatitude'].value ,self.metadata['Exif.GPSInfo.GPSLatitudeRef'].value),
                                dms_to_decimal(self.metadata['Exif.GPSInfo.GPSLongitude'].value,self.metadata['Exif.GPSInfo.GPSLongitudeRef'].value))
            except:
                self._latlon = None
        return self._latlon
                    
    def process(self,
                 vision_features: dict=ImageLibrary.DEFAULT_SETTINGS['vision_features'],
                 reverse_geocoding: dict=ImageLibrary.DEFAULT_SETTINGS['reverse_geocoding'],
                 translate: str=ImageLibrary.DEFAULT_SETTINGS['translate'],
                 replace_labels: bool=ImageLibrary.DEFAULT_SETTINGS['replace_labels'],
                 rotate_images: bool=ImageLibrary.DEFAULT_SETTINGS['rotate_images'],
                 reannotate: bool=False):
        if self.library.settings.is_synology:
            self.create_all_thumbnails()
            
        if rotate_images:
            self.remove_exif_orientation()
            
        if not self.is_annotated or reannotate:
            if not hasattr(self.library,'gapi'):
                self.library.log('GAPI not initialized')
                return
            
            (labels,faces)=self.library.gapi.annotate(self.get_thumbnail('B').as_blob(),vision_features,translate)
            if self.latlon and reverse_geocoding:
                labels.extend(self.library.gapi.getlocation(self.latlon,translate))
            
            if replace_labels:
                self.labels = labels
            else:
                self.labels = self.labels+labels
            
            if 'FACE_DETECTION' in vision_features:
                # convert vertices to (x,y,width,height) with normalized values
                (width,height)=(self.get_thumbnail('B').width,self.get_thumbnail('B').height)
                faces = [(round(face[0][0]/width,7),round(face[0][1]/height,7),round((face[2][0]-face[0][0])/width,7),round((face[2][1]-face[0][1])/height,7)) for face in faces]
            
                # delete already tagged faces:
                self.clear_faces()
                
                # add found faces
                [self.add_face(rect) for rect in faces]
            
            self.is_annotated = True
            self.library.log ('Found {} label(s) and {} face(s): {}'.format(len(self.labels),len(self.faces),self.file_path))
    
        
    class _Face:
        THUMBNAIL_SIZE = (150,150)
        LOSSLESS = False
        
        def __init__(self,image,index:int,name:str=None,rect:List[float]=None):
            self.image = image
            self.index = index
            if type(name) == str: self.name = name
            if rect: self.rect = rect
        
        def check_metadata(self):
            base = 'Xmp.MP.RegionInfo'
            if not base in self.image.metadata:
                self.image.metadata[base] = pyexiv2.xmp.XmpTag(base, 'type=Struct')
                self.image.changed = True
            base = 'Xmp.MP.RegionInfo/MPRI:Regions'
            if not base in self.image.metadata:
                self.image.metadata[base] = pyexiv2.xmp.XmpTag(base, [""])
                self.image.changed = True
                
        @property
        def rect_tag(self):
            return f'Xmp.MP.RegionInfo/MPRI:Regions[{self.index}]/MPReg:Rectangle'
                
        @property
        def name_tag(self):
            return f'Xmp.MP.RegionInfo/MPRI:Regions[{self.index}]/MPReg:PersonDisplayName'
                
        @property
        def ignored_tag(self):
            return f'Xmp.MP.RegionInfo/MPRI:Regions[{self.index}]/MPReg:Ignored'
                
        @property
        def thumbnail_file(self):
            return os.path.join(self.image.thumb_path,f'face_{self.index}.jpg')
        
        def clear_tags(self):
            self.image.metadata.pop(self.rect_tag,None)
            self.image.metadata.pop(self.name_tag,None)
            self.image.metadata.pop(self.ignored_tag,None)
                
        def delete(self):
            # clear metadata and remove thumbnail
            self.clear_tags()
            if os.path.exists(self.thumbnail_file):
                os.remove(self.thumbnail_file)
            
            # update index of remaining faces
            for face in self.image.faces[self.index:]:
                face.index = face.index-1
            
            # remove face from list
            self.image._faces.remove(self)
            self.image.changed = True
            
        def ignore(self):
            self.name = ''
            self.ignored = True
            
        @property
        def ignored(self):
            if not self.ignored_tag in self.image.metadata:
                return False
            return self.image.metadata[self.ignored_tag].value == 'True'
        
        @ignored.setter
        def ignored(self,value):
            self.check_metadata()
            self.image.metadata[self.ignored_tag] = pyexiv2.xmp.XmpTag(self.ignored_tag, str(bool(value)))
            self.image.changed = True
            
        @property
        def index(self):
            return self._index
        
        @index.setter
        def index(self,value):
            if not hasattr(self,'_index'):
                self._index = value
            else:
                #remove thumbnail if exists
                if os.path.exists(self.thumbnail_file):
                    os.remove(self.thumbnail_file)
                
                #backup data
                name = self.name
                rect = self.rect
                ignored = self.ignored
                self.clear_tags()
                
                #change index
                self._index = value
                
                #restore data
                self.name = name
                self.rect = rect
                self.ignored = ignored
            
        @property
        def name(self):
            if self.rect and not self.name_tag in self.image.metadata:
                self.name = '' # add missing name tag
            if not self.name_tag in self.image.metadata:
                return None
            return self.image.metadata[self.name_tag].value
        
        @name.setter
        def name(self,value):
            self.check_metadata()
            self.image.metadata[self.name_tag] = pyexiv2.xmp.XmpTag(self.name_tag, value)
            self.image.changed = True
            
        @property
        def rect(self):
            if not self.rect_tag in self.image.metadata:
                return None
            (x,y,w,h) = [float(x) for x in self.image.metadata[self.rect_tag].value.split(', ')]
            
            if any([val > 1 or val < 0 for val in [x,y,w+x,h+y]]):
                self.rect = [x,y,w,h] # reset rect to be in range [0,1]
                return self.rect
            return [x,y,w,h]
        
        @rect.setter
        def rect(self,values:List[float]):
            if hasattr(self, '_thumbnail'):
                delattr(self,'_thumbnail')
            self.check_metadata()
            (x,y,w,h) = values
            # ensure rect is in range [0,1]
            values = [min(1,max(0,x)), min(1,max(0,y)), max(0,min(1,w+x)-x), max(0,min(1,h+y)-y)]
            self.image.metadata[self.rect_tag] = pyexiv2.xmp.XmpTag(self.rect_tag, '{}, {}, {}, {}'.format(*(values)))
            self.image.changed = True
            
        @property
        def thumbnail(self):
            if not self.rect:
                raise Exception('No face tag defined')
            if not hasattr(self, '_thumbnail'):
                if os.path.exists(self.thumbnail_file):
                    self._thumbnail = jpegtran.JPEGImage(self.thumbnail_file)
                else:
                    if self.LOSSLESS:
                        thumb = self.image.get_thumbnail('XL')
                        (width,height) = (thumb.width,thumb.height)
                        (x,y,w,h) = self.rect
                        (x,y,w,h) = (x*width, y*height, w*width, h*height)
                        # jpeg lossless cropping requires (at worst) a multiple of 16x16 pixels, since faces could be small, we try 8x8 first
                        try:
                            (x2,y2) = (x-(x % 8),y-(y % 8))
                            (x2,y2,w2,h2) = (int(x2),int(y2),int(w+(x-x2)),int(h+(y-y2)))
                            self._thumbnail = thumb.crop(x2,y2,w2,h2).downscale(*self.image.get_downscale_size(w2,h2,*self.THUMBNAIL_SIZE),90)
                        except:
                            (x2,y2) = (x-(x % 16),y-(y % 16))
                            (x2,y2,w2,h2) = (int(x2),int(y2),int(w+(x-x2)),int(h+(y-y2)))
                            self._thumbnail = thumb.crop(x2,y2,w2,h2).downscale(*self.image.get_downscale_size(w2,h2,*self.THUMBNAIL_SIZE),90)
                    else:
                        thumb = PIL.Image.open(io.BytesIO(self.image.get_thumbnail('XL').as_blob()))
                        (width,height) = thumb.size
                        (x,y,w,h) = self.rect
                        (x1,y1,x2,y2) = (x*width, y*height, (x+w)*width, (y+h)*height)
                        thumb = thumb.crop((x1,y1,x2,y2))
                        thumb.thumbnail(self.THUMBNAIL_SIZE, PIL.Image.ANTIALIAS)
                        buffered = io.BytesIO()
                        thumb.save(buffered, format="JPEG", quality=90)
                        self._thumbnail = jpegtran.JPEGImage(blob=buffered.getvalue())
                    self._thumbnail.save(self.thumbnail_file)
                    
            return self._thumbnail