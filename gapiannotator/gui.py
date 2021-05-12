# -*- coding: utf-8 -*-
#
# Copyright (C) 2021, Sebastian Nagel.
#
# This file is part of the module 'gapiannotator' and is released under
# the MIT License: https://opensource.org/licenses/MIT
#
from urllib.parse import parse_qs
import os, json
import re
import mimetypes
import threading
import traceback

import asyncio
import aiohttp
from aiohttp import web
import sass

from . import PKG_ROOT
from .gapi import Gapi

FACE_TYPES = ['untagged','ignored','all']


class WebGUIServer(threading.Thread):
    def __init__(self,
                 library,
                 addr: str='0.0.0.0',
                 port: int=8000):
        self.library = library
        self.addr = addr
        self.port = port
        self.html = WebGUIServer._fileloader('web-templates','.html')
        self.htdocs = WebGUIServer._fileloader('.',mode='rb',return_mime=True)
        self.websockets = []
        self.checkTable()
        self.add_listeners()
        
        threading.Thread.__init__(self)
        self.daemon = True
        
    def add_listeners(self):
        self.library.event.add('log',lambda message:
            self.websocket_send_all({'cmd':'new_log_entry','data':message}))
        self.library.event.add('remaining_files',lambda num_files:
            self.websocket_send_all({'cmd':'remaining_files','data':num_files}))
        self.library.event.add('new_image',self.new_image)
        self.library.event.add('deleted_image',lambda imgindex:
            self.websocket_send_all({'cmd':'deleted_image', 'data':imgindex}))
        
    def new_image(self,image):
        faces = image.untagged_faces
        if (faces):
            data = [{
                    'index': image.index,
                    'src': f"./image/{image.index}",
                    'faces': [{'index':face.index, 
                               'name':face.name,
                               'src': f"./image/{image.index}/face/{face.index}"} 
                              for face in faces]
                    }]
            self.websocket_send_all({'cmd':'new_faces', 'data':data})
         
    def checkTable(self):
        self.library.db.execute("""CREATE TABLE IF NOT EXISTS knownnames(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE);""",True)
    
    def run(self):
        self.library.log(f'Staring WebGUIServer on port {self.port}')
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(self.start_server())
        self.loop.run_forever()
        
    def create_runner(self):
        app = web.Application()
        app.add_routes([
            web.get(r'/ws', self.websocket_handler),
            web.get(r'/{path:.*}', self.do_GET),
            web.post(r'/{path:.*}', self.do_POST),
        ])
        return web.AppRunner(app)
        
    async def start_server(self):
        runner = self.create_runner()
        await runner.setup()
        site = web.TCPSite(runner, self.addr, self.port)
        await site.start()
        
    def websocket_send_all(self,data):
        message = json.dumps(data)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            loop.create_task(self._websocket_send_all(message))
        else:
            asyncio.run(self._websocket_send_all(message))
            
    def websocket_send_single(self,ws,data):
        message = json.dumps(data)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            loop.create_task(self._websocket_send_single(ws,message))
        else:
            asyncio.run(self._websocket_send_single(ws,message))
        
    async def _websocket_send_all(self, message):
        for ws in self.websockets:
            await self._websocket_send_single(ws, message)
                
    async def _websocket_send_single(self, ws, message):
        try:
            await ws.send_str(message)
        except ConnectionResetError:
            #print('Connection lost to websocket')
            try:
                self.websockets.remove(ws)
            except:
                pass
    
    async def websocket_handler(self,request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.websockets.append(ws)
    
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                if msg.data == 'close':
                    await ws.close()
                else:
                    try:
                        data = json.loads(msg.data)
                        self.api_call(data['cmd'],data['data'],ws)
                    except:
                        print('Api call failed with data: {}'.format(msg.data))
                        traceback.print_exc() 
                        
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print('ws connection closed with exception %s' % ws.exception())
        self.websockets.remove(ws)
        
        return ws
    
    def get_files(self,face_type='untagged',limit=-1,lastimageid=None):
        if face_type == 'untagged':
            where = 'hasUntaggedFaces=1'
        elif face_type == 'ignored':
            where = 'hasIgnoredFaces=1'
        elif face_type == 'all':
            where = 'hasFaces=1'
            
        order = 'modifedTimesamp DESC, id DESC'
        
        if lastimageid:
            sql = f"""SELECT filePath FROM files 
                      WHERE {where}
                      ORDER BY {order}
                      LIMIT {limit} OFFSET 
                          (SELECT RowNum-1 FROM 
                               (SELECT ROW_NUMBER () OVER (ORDER BY {order}) RowNum, id FROM files 
                                WHERE {where}
                                ORDER BY {order})
                           WHERE id = {lastimageid})"""
        else:
            sql = f"SELECT filePath FROM files WHERE {where} ORDER BY {order} LIMIT {limit};"
        
        try:
            return [file_path for (file_path,) in self.library.db.execute(sql).fetchall()]
        except:
            return []
    
    @property
    def known_names(self):
        if not hasattr(self,'_known_names'):
            self._known_names = [name for (name,) in self.library.db.execute("SELECT name FROM knownnames").fetchall()]
        return self._known_names
        
    @known_names.setter
    def known_names(self,value):
        if not value in self.known_names:
            self._known_names.append(value)
            self.library.db.execute(f"INSERT INTO knownnames (name) VALUES ('{value}');",True)
    
    def ignore_faces(self,images):
        response = []
        for imgindex, faces in images.items():
            file_path=self.library.db.execute(f"SELECT filePath FROM files WHERE id={imgindex};").fetchone()
            if file_path and os.path.exists(file_path[0]):
                img = self.library.get_image(file_path[0])
                for faceidx in faces:
                    img.faces[faceidx-1].ignore()
                img.save()
                response.append({
                    'index': img.index,
                    'src': f"./image/{img.index}",
                    'faces': [{'index':faceidx, 
                               'name':img.faces[faceidx-1].name,
                               'ignored':img.faces[faceidx-1].ignored,
                               'src': f"./image/{img.index}/face/{faceidx}"} 
                              for faceidx in faces]
                    })
        return response
    
    def delete_faces(self,images):
        response = []
        for imgindex, faces in images.items():
            file_path=self.library.db.execute(f"SELECT filePath FROM files WHERE id={imgindex};").fetchone()
            if file_path and os.path.exists(file_path[0]):
                img = self.library.get_image(file_path[0])
                faces.sort(reverse=True)
                for faceidx in faces:
                    img.faces[faceidx-1].delete()
                img.save()
                response.append({
                    'index': img.index,
                    'src': f"./image/{img.index}",
                    'faces': [{'index':face.index, 
                               'name':face.name,
                               'ignored':face.ignored,
                               'src': f"./image/{img.index}/face/{face.index}"} 
                              for face in img.faces] # return remaining faces on delete
                    })
        return response
    
    def name_faces(self,images,name):
        response = []
        for imgindex, faces in images.items():
            file_path=self.library.db.execute(f"SELECT filePath FROM files WHERE id={imgindex};").fetchone()
            if file_path and os.path.exists(file_path[0]):
                img = self.library.get_image(file_path[0])
                for faceidx in faces:
                    img.faces[faceidx-1].name = name
                    img.faces[faceidx-1].ignored = False
                img.save()
                response.append({
                    'index': img.index,
                    'src': f"./image/{img.index}",
                    'faces': [{'index':faceidx, 
                               'name':img.faces[faceidx-1].name,
                               'ignored':img.faces[faceidx-1].ignored,
                               'src': f"./image/{img.index}/face/{faceidx}"} 
                              for faceidx in faces]
                    })
        self.known_names = name
        return response

    def delete_duplicates(self,images):
        for idx in images:
            try:
                (filePath,)=self.library.db.execute(f"SELECT filePath FROM files WHERE id = {idx};").fetchone()
                if os.path.exists(filePath):
                    os.remove(filePath) 
                    self.library.delete(filePath,False)
            except:
                pass

        return None
    
    def get_image_bytes(self,imageid,faceid=None):
        file_path=self.library.db.execute(f"SELECT filePath FROM files WHERE id={imageid};").fetchone()
        if file_path and os.path.exists(file_path[0]):
            img = self.library.get_image(file_path[0])
            if not faceid:
                return img.get_thumbnail('B').as_blob()
            if faceid <= len(img.faces):
                return img.faces[faceid-1].thumbnail.as_blob()
        return b''
    
    def load_faces(self,numfaces=50,lastimageid=None,lastfaceid=None,facetype=FACE_TYPES[0]):
        data = []
        if not facetype in FACE_TYPES:
            facetype = FACE_TYPES[0]
        
        files = self.get_files(facetype,numfaces,lastimageid)
        images = self.library.get_images(files)
        faceidx = 0
        for image in images:
            if faceidx >= numfaces: break
        
            if facetype == 'untagged':
                faces = image.untagged_faces
            elif facetype == 'ignored':
                faces = image.ignored_faces
            elif facetype == 'all':
                faces = image.faces
                
            if image.index == lastimageid:
                faces = [face for face in faces if face.index > lastfaceid]
            
            if (faces):
                faces = faces[:min(len(faces),numfaces-faceidx)]
                data.append({
                    'index': image.index,
                    'src': f"./image/{image.index}",
                    'faces': [{'index':face.index, 
                               'name':face.name,
                               'ignored':face.ignored,
                               'src': f"./image/{image.index}/face/{face.index}"} 
                              for face in faces]
                    })
                faceidx += len(faces)
                if faceidx >= numfaces: break
        return data
    
    def load_duplicates(self,similarity=0.99):
        data = {}
        
        maxdist = int(round(self.library.settings.hash_size**2 * (1-similarity)))
        duplicates = [(path1,path2,dist) for (path1,path2,dist) in 
                          self.library.db.execute(f"""SELECT b.filePath, c.filePath, a.dist from similarity a 
                                            INNER JOIN files b ON b.id = a.id1 
                                            INNER JOIN files c ON c.id = a.id2
                                            WHERE a.dist <= {maxdist};""").fetchall()
                      if os.path.exists(path1) and os.path.exists(path2)]
        for (path1,path2,dist) in duplicates:
            img1 = self.library.get_image(path1)
            img2 = self.library.get_image(path2)
            if not img1.index in data:
                data[img1.index] = [{
                    'index': img1.index,
                    'src': f"./image/{img1.index}",
                    'file_path': img1.file_path,
                    'file_name': img1.file_name,
                    'size': img1.file_size,
                    'date': img1.date,
                    'dist': 0,
                    }]
            data[img1.index].append({
                        'index': img2.index,
                        'src': f"./image/{img2.index}",
                        'file_path': img2.file_path,
                        'file_name': img2.file_name,
                        'size': img2.file_size,
                        'date': img2.date,
                        'dist': dist
                    })
            if not img2.index in data:
                data[img2.index] = [{
                    'index': img2.index,
                    'src': f"./image/{img2.index}",
                    'file_path': img2.file_path,
                    'file_name': img2.file_name,
                    'size': img2.file_size,
                    'date': img2.date,
                    'dist': 0
                }]
            data[img2.index].append({
                        'index': img1.index,
                        'src': f"./image/{img1.index}",
                        'file_path': img1.file_path,
                        'file_name': img1.file_name,
                        'size': img1.file_size,
                        'date': img1.date,
                        'dist': dist
                    })
            
        # Fuse similar groups
        groups = {}
        for group in data.values():
            group.sort(key=lambda x: x['index'], reverse=False)
            group.sort(key=lambda x: x['date'], reverse=False)
            group.sort(key=lambda x: x['size'], reverse=True)
            ref = group[0]['index']
            if not ref in groups:
                groups[ref] = group
            else:
                groups[ref].extend([image for image in group if image['index'] not in [img['index'] for img in groups[ref]]])
                groups[ref].sort(key=lambda x: x['date'], reverse=False)
                groups[ref].sort(key=lambda x: x['size'], reverse=True)
             
        # Order groups by date and number of images
        groups = groups.items()
        groups = sorted(groups,key=lambda x: x[1][0]['date'],reverse=True)
        groups = sorted(groups,key=lambda x: len(x[1]),reverse=True)
        groups = dict(groups)
        order = list(groups.keys())
        return {'order':order,'groups':groups}

    def keep_duplicates(self,images):
        for idx in images:
            self.library.db.execute(f"DELETE FROM similarity WHERE id1 = {idx} OR id2 = {idx};",True)
        return images

    def load_logs(self):
        return self.library.log_queue
    
    def api_call(self,cmd,data,ws=None):
        if cmd == 'load_settings':
            response = self.library.settings.to_dict()
        elif cmd == 'save_settings':
            self.library.settings.update(data)
            response = self.library.settings.to_dict()
        elif cmd in ['load_faces','name_faces','ignore_faces','delete_faces','load_duplicates','load_logs','delete_duplicates','keep_duplicates']:
            response = getattr(self,cmd)(**data)
        elif cmd in ['process']:
            def process():
                getattr(self.library,cmd)(**data)
            thread = threading.Thread(target=process, args=())
            thread.daemon = True
            thread.start()
            response = {}
        elif cmd == 'known_names':
            response = self.known_names
        elif cmd == 'path_exists':
            response = {'abspath':os.path.abspath(data),
                        'exists':os.path.exists(data),
                        'isdir':os.path.isdir(data),
                        'isfile':os.path.isfile(data)}
        elif cmd in ['check_apikey','check_credentials']:
            response = {'abspath':os.path.abspath(data),
                        'exists':os.path.exists(data),
                        'isdir':os.path.isdir(data),
                        'isfile':os.path.isfile(data),
                        'valid': getattr(Gapi,cmd)(data)}
        else:
            return None
        
        response = {'cmd': cmd, 'data': response}
        if not cmd.startswith('load'):
            self.websocket_send_all(response)
        elif not type(ws) == type(None):
            self.websocket_send_single(ws,response)
            
        return response
    
    async def do_GET(self,request):
        # redirects
        if re.match(r'^/(facetagger|annotation|duplicates|settings|logs)?$', request.path) and not self.library.settings.valid_credentials:
            raise web.HTTPPermanentRedirect('/setup')
        elif re.match(r'^/setup?$', request.path) and self.library.settings.valid_credentials:
            raise web.HTTPPermanentRedirect('/settings')
        
        try:
            status=200
            content_type='text/html'
            if re.match(r'^/(facetagger|annotation|duplicates|settings|logs|setup)?$', request.path):
                content = self.html.main.format(content="").encode('utf-8') # content will be set dynamically on the javascript side
            elif re.match(r'^/web/', request.path):
                scss_file = os.path.join(PKG_ROOT,'.'+request.path[:-3]+'scss')
                if (request.path.endswith('.css') and os.path.exists(scss_file)):
                    content = sass.compile( filename=scss_file ).encode('utf-8')
                    content_type = 'text/css'
                else:
                    (content,content_type) = self.htdocs[request.path]
                status = 200 if content else 404
            elif re.search(r'^/image/(?P<imageid>\d+)/face/(?P<faceid>\d+)/?$', request.path):
                data = re.search(r'^/image/(?P<imageid>\d+)/face/(?P<faceid>\d+)/?$', request.path);
                content = self.get_image_bytes(int(data.group('imageid')),int(data.group('faceid')))
                content_type = 'image/jpeg'
                status = 200 if content else 404
            elif re.search(r'^/image/(?P<imageid>\d+)/?$', request.path):
                data = re.search(r'^/image/(?P<imageid>\d+)/?$', request.path);
                content = self.get_image_bytes(int(data.group('imageid')))
                content_type = 'image/jpeg'
                status = 200 if content else 404
            else:
                content = b''
                status = 404
        except Exception as e:
            print(f'Error while handling GET request {request.path}')
            print(e)
            content = b''
            content_type='text/html'
            status = 500
        return web.Response(body=content, status=status, content_type=content_type)

    async def do_POST(self,request):
        content_type = 'application/json'
        try:
            if re.search(r'^/api/(?P<cmd>[^/]*)/$', request.path):
                if request.can_read_body:
                    post_data = json.loads(parse_qs(await request.text())['data'][0])
                else:
                    post_data = None
                status = 200
                data = re.search(r'^/api/(?P<cmd>[^/]*)/$', request.path)
                response = self.api_call(data.group('cmd'),post_data)
                content = json.dumps(response).encode('utf-8')
            else:
                content = b''
                status = 404
        except Exception as e:
            print(f'Error while handling POST request {request.path}')
            traceback.print_exc() 
            data = {"cmd": "error", "data": str(e)}
            content = json.dumps(data).encode('utf-8')
            status = 200
        return web.Response(body=content, status=status, content_type=content_type)

    class _fileloader:
        def __init__(self, path='.', ext='', mode='r', return_mime=False):
            self.path = path
            self.ext = ext
            self.mode = mode
            self.return_mime = return_mime
        
        def openfile(self,file_name):
            file_path = os.path.abspath(os.path.join(PKG_ROOT, self.path, '.'+os.path.sep+file_name))
            if os.path.exists(file_path) and os.path.isfile(file_path):
                with open(file_path,mode=self.mode) as f:
                    content = f.read()
                mime_type = mimetypes.guess_type(file_path)[0]
            else:
                content = mime_type = None
            return (content,mime_type) if self.return_mime else content
        
        def __getattr__(self,attr):
            return self.openfile(attr+self.ext)
        
        def __getitem__(self,item):
            return self.openfile(item+self.ext)
