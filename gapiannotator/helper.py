# -*- coding: utf-8 -*-
#
# Copyright (C) 2021, Sebastian Nagel.
#
# This file is part of the module 'gapiannotator' and is released under
# the MIT License: https://opensource.org/licenses/MIT
#
import json, os
from typing import Any
from collections.abc import Callable, Iterable
    
class sqlitedb:
    def __init__(self,db_file: str):
        import threading
        import sqlite3
        self.lock = threading.Lock()
        self.db_file = db_file
        self.conn = sqlite3.connect(self.db_file,check_same_thread=False)
        self._load_libs()
    
    def _load_libs(self):
        from . import PKG_ROOT
        # EXAMPLE: SELECT photo_id, hexhammdist(photo_hash, ?) AS hd FROM photos WHERE hd <= 9;
        hexhammdist_lib = os.path.join(PKG_ROOT,"sqlite-hexhammdist","sqlite-hexhammdist.so")
        self._hexhammdist = False
        if os.path.exists(hexhammdist_lib):
            try:
                self.conn.enable_load_extension(True)
                self.execute(f"SELECT load_extension('{hexhammdist_lib}', 'hexhammdist_init');", True)
                self._hexhammdist = True
            except:
                pass
        
            
    def execute(self,sql: str,commit: bool=False):
        #serialize all commands
        with self.lock:
            result = self.conn.cursor().execute(sql)
            if commit:
                self.conn.commit()
        return result
    
    def close(self):
        self.conn.close()
        
    @property
    def hexhammdist(self):
        return self._hexhammdist
        
class Settings:
    def __init__(self, db:sqlitedb, default: dict={}):
        self._db = db
        self._checkTable()
        self._settings = dict(default,**{key : json.loads(value) for (key,value) in self._db.execute("SELECT key,value FROM settings;").fetchall()})
        
    def _checkTable(self):
        self._db.execute("""CREATE TABLE IF NOT EXISTS settings(
            id INTEGER PRIMARY KEY,
            key TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL);""",True)
        
    def _get_settings(self,key:str):
        if not key.startswith('_'):
            if key in self._settings:
                return self._settings[key]
            else:
                return None
        
    def _set_settings(self,key:str,value:Any):
        esc_key = key.replace("'", "''")
        esc_value = json.dumps(value).replace("'", "''")
        if not key in self._settings or self._settings[key] != value:
            self._db.execute(f"REPLACE INTO settings (key, value) VALUES ('{esc_key}','{esc_value}');",True)
            self._settings[key] = value
            self.on_settings_changed([key])
        
    def _remove_settings(self,key:str,default:Any=None):
        esc_key = key.replace("'", "''")
        self._db.execute(f"DELETE FROM settings WHERE key = '{esc_key}';",True) 
        return self._settings.pop(key,default)
        
    def __getattr__(self,key:str):
        if key.startswith('_'):
            return super(Settings, self).__getattr__(key)
        else:
            return self._get_settings(str(key))
        
    def __setattr__(self,key:str,value:Any):
        if key.startswith('_'):
            super(Settings, self).__setattr__(key, value)
        else:
            self._set_settings(str(key), value)

    def clear(self):
        esc_keys = ", ".join(["'{}'".format(str(key).replace("'", "''")) for key in self._settings.keys()])
        self._db.execute(f"DELETE FROM settings WHERE key IN '{esc_keys}';",True) 
        self._settings.clear()

    def update(self, iterable:Iterable):
        if (type(iterable) == dict):
            iterable = iterable.items()
        esc_values = ", ".join(["('{}','{}')".format(str(key).replace("'", "''"),json.dumps(value).replace("'", "''"))  for (key,value) in iterable])
        self._db.execute(f"REPLACE INTO settings (key, value) VALUES {esc_values};",True)
        
        oldsettings = self._settings.copy()
        self._settings.update(iterable)
        changed_settings = []
        for (key,value) in self._settings.items():
            if value != oldsettings[key]:
                changed_settings.append(key)
        
        if changed_settings:
            self._on_settings_changed(changed_settings)
            
    def set_settings_changed_listener(self,listener):
        self._on_settings_changed = listener
        
    def _on_settings_changed(self,changed_settings):
        pass
            
    def __delattr__(self,key:str): self._remove_settings(key)
    def __delitem__(self,key:str): self._remove_settings(key)
    def __getitem__(self,key:str): return self._get_settings(str(key))
    def __setitem__(self,key:str,value:Any): self._set_settings(str(key), value)
    def __repr__(self): return repr(self._settings)
    def __len__(self): return len(self._settings)
    def __contains__(self, item:str): return item in self._settings
    def __iter__(self): return iter(self._settings)
    def pop(self, key:str, default:Any=None): return self._remove_settings(key,default)
    def to_dict(self): return self._settings
    def copy(self): return self._settings.copy()
    def keys(self): return self._settings.keys()
    def values(self): return self._settings.values()
    def items(self): return self._settings.items()
        
class EventHandler(object):
    def __init__(self):
        self.handlers = {}
    
    def add(self, name:str, handler:Callable, *args, **kwargs):
        if (not name in self.handlers):
            self.handlers[name] = []
        for h in self.handlers[name]:
            if (h[0] == handler):
                h[1]=args
                h[2]=kwargs
                return self
        self.handlers[name].append((handler,args,kwargs))
        return self
    
    def remove(self, name:str, handler:Callable):
        if (name in self.handlers):
            for h in self.handlers[name]:
                if (h[0] == handler):
                    self.handlers[name].remove(h)
        return self
    
    def fire(self, name:str, *args, **kwargs):
        if (name in self.handlers):
            for handler in self.handlers[name]:
                handler[0](*(*args,*handler[1]), **{**kwargs, **handler[2]})
                
    __call__ = fire

def rgb_to_name(requested_colour: str):
    import webcolors
    webcolors.CSS3_HEX_TO_NAMES_SIMPLE = {'#E7E7E7': 'gray white', '#f0f8ff': 'blue', '#faebd7': 'white', '#00ffff': 'turquoise', '#7fffd4': 'turquoise', '#f0ffff': 'azure', '#f5f5dc': 'beige', '#ffe4c4': 'beige', '#000000': 'black', '#ffebcd': 'beige', '#0000ff': 'blue', '#8a2be2': 'purple', '#a52a2a': 'brown', '#deb887': 'brown', '#5f9ea0': 'blue green', '#7fff00': 'green', '#d2691e': 'brown', '#ff7f50': 'orange', '#6495ed': 'blue', '#fff8dc': 'beige', '#dc143c': 'red', '#00008b': 'blue', '#008b8b': 'blue green', '#b8860b': 'brown', '#a9a9a9': 'gray', '#006400': 'green', '#bdb76b': 'khaki', '#8b008b': 'purple', '#556b2f': 'green', '#ff8c00': 'orange', '#9932cc': 'purple', '#8b0000': 'red', '#e9967a': 'red brown', '#8fbc8f': 'green', '#483d8b': 'blue purple', '#2f4f4f': 'green gray', '#00ced1': 'turquoise', '#9400d3': 'purple', '#ff1493': 'pink', '#00bfff': 'blue', '#696969': 'gray', '#1e90ff': 'blue', '#b22222': 'red brown', '#fffaf0': 'white', '#228b22': 'green', '#ff00ff': 'pink', '#dcdcdc': 'gray', '#f8f8ff': 'white', '#ffd700': 'yellow', '#daa520': 'brown', '#808080': 'gray', '#008000': 'green', '#adff2f': 'green', '#f0fff0': 'light green', '#ff69b4': 'pink', '#cd5c5c': 'red brown', '#4b0082': 'blue purple', '#fffff0': 'white', '#f0e68c': 'khaki', '#e6e6fa': 'lavender', '#fff0f5': 'lavender', '#7cfc00': 'green', '#fffacd': 'light yellow', '#add8e6': 'light blue', '#f08080': 'red', '#e0ffff': 'light turquoise', '#fafad2': 'beige', '#d3d3d3': 'gray', '#90ee90': 'light green', '#ffb6c1': 'light pink', '#ffa07a': 'light orange', '#20b2aa': 'turquoise', '#87cefa': 'light blue', '#778899': 'gray', '#b0c4de': 'light blue', '#ffffe0': 'light yellow', '#00ff00': 'green', '#32cd32': 'green', '#800000': 'red brown', '#66cdaa': 'green', '#0000cd': 'blue', '#ba55d3': 'purple', '#9370db': 'purple', '#3cb371': 'green', '#7b68ee': 'blue', '#00fa9a': 'green', '#48d1cc': 'turquoise', '#c71585': 'pink', '#191970': 'blue', '#f5fffa': 'light green', '#ffe4b5': 'beige', '#ffdead': 'beige', '#000080': 'blue', '#fdf5e6': 'beige', '#808000': 'green', '#6b8e23': 'green', '#ffa500': 'orange', '#ff4500': 'orangered', '#da70d6': 'purple', '#eee8aa': 'beige', '#98fb98': 'green', '#afeeee': 'turquoise', '#ffefd5': 'beige', '#ffdab9': 'beige', '#cd853f': 'brown', '#ffc0cb': 'pink', '#dda0dd': 'purple', '#b0e0e6': 'turquoise', '#800080': 'purple', '#ff0000': 'red', '#bc8f8f': 'brown', '#4169e1': 'blue', '#8b4513': 'brown', '#fa8072': 'salmon', '#f4a460': 'brown', '#2e8b57': 'green', '#fff5ee': 'white', '#a0522d': 'brown', '#c0c0c0': 'gray', '#87ceeb': 'blue', '#6a5acd': 'blue', '#708090': 'gray', '#fffafa': 'white', '#00ff7f': 'green', '#4682b4': 'blue', '#d2b48c': 'brown', '#008080': 'green', '#d8bfd8': 'light purple', '#ff6347': 'orange', '#40e0d0': 'turquoise', '#ee82ee': 'pink', '#f5deb3': 'beige', '#ffffff': 'white', '#f5f5f5': 'white', '#ffff00': 'yellow', '#9acd32': 'green' }

    color_names = []
    def closest_colour(requested_colour,colordict):
        min_colours = {}
        for key, name in colordict.items():
            r_c, g_c, b_c = webcolors.hex_to_rgb(key)
            rd = (r_c - requested_colour[0]) ** 2
            gd = (g_c - requested_colour[1]) ** 2
            bd = (b_c - requested_colour[2]) ** 2
            min_colours[(rd + gd + bd)] = name
        return min_colours[min(min_colours.keys())]
    try:
        color_names.append(webcolors.rgb_to_name(requested_colour))
    except ValueError:
        color_names.append(closest_colour(requested_colour, webcolors.CSS3_HEX_TO_NAMES))
    
    color_names.append(closest_colour(requested_colour, webcolors.CSS3_HEX_TO_NAMES_SIMPLE))
    return color_names


def dms_to_decimal(dms, ref):
    dms = [float(x) for x in dms]
    try:
        degrees = dms[0][0] / dms[0][1]
        minutes = dms[1][0] / dms[1][1] / 60.0
        seconds = dms[2][0] / dms[2][1] / 3600.0
    except:
        degrees = dms[0]
        minutes = dms[1] / 60.0
        seconds = dms[2] / 3600.0

    if ref in ['S', 'W']:
        degrees = -degrees
        minutes = -minutes
        seconds = -seconds

    return round(degrees + minutes + seconds, 5)

def size_fmt(num):
    for unit in ['B','KB','MB','GB','TB','PB','EB','ZB']:
        if abs(num) < 1000.0:
            return "%3.2f%s" % (num, unit)
        num /= 1024.0
    return "%.2f%s" % (num, 'YB')