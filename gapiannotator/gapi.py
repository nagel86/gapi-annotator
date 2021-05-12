# -*- coding: utf-8 -*-
#
# Copyright (C) 2021, Sebastian Nagel.
#
# This file is part of the module 'gapiannotator' and is released under
# the MIT License: https://opensource.org/licenses/MIT
#
import os, errno
from typing import Tuple

import googlemaps
from google.cloud import vision_v1 as vision
from google.cloud import translate_v2 as translate

from .helper import rgb_to_name, sqlitedb

class Gapi():
    VISION_FEATURES = {'LABEL_DETECTION':0.75,'FACE_DETECTION':0.5,'LANDMARK_DETECTION':0.75,'LOGO_DETECTION':0.75,'IMAGE_PROPERTIES':0.1,'TEXT_DETECTION':0.0,'OBJECT_LOCALIZATION':0.75}
    SUPPORTED_LANGUAGES = [{'language': 'af', 'name': 'Afrikaans'}, {'language': 'sq', 'name': 'Albanian'}, {'language': 'am', 'name': 'Amharic'}, {'language': 'ar', 'name': 'Arabic'}, {'language': 'hy', 'name': 'Armenian'}, {'language': 'az', 'name': 'Azerbaijani'}, {'language': 'eu', 'name': 'Basque'}, {'language': 'be', 'name': 'Belarusian'}, {'language': 'bn', 'name': 'Bengali'}, {'language': 'bs', 'name': 'Bosnian'}, {'language': 'bg', 'name': 'Bulgarian'}, {'language': 'ca', 'name': 'Catalan'}, {'language': 'ceb', 'name': 'Cebuano'}, {'language': 'ny', 'name': 'Chichewa'}, {'language': 'zh-CN', 'name': 'Chinese (Simplified)'}, {'language': 'zh-TW', 'name': 'Chinese (Traditional)'}, {'language': 'co', 'name': 'Corsican'}, {'language': 'hr', 'name': 'Croatian'}, {'language': 'cs', 'name': 'Czech'}, {'language': 'da', 'name': 'Danish'}, {'language': 'nl', 'name': 'Dutch'}, {'language': 'en', 'name': 'English'}, {'language': 'eo', 'name': 'Esperanto'}, {'language': 'et', 'name': 'Estonian'}, {'language': 'tl', 'name': 'Filipino'}, {'language': 'fi', 'name': 'Finnish'}, {'language': 'fr', 'name': 'French'}, {'language': 'fy', 'name': 'Frisian'}, {'language': 'gl', 'name': 'Galician'}, {'language': 'ka', 'name': 'Georgian'}, {'language': 'de', 'name': 'German'}, {'language': 'el', 'name': 'Greek'}, {'language': 'gu', 'name': 'Gujarati'}, {'language': 'ht', 'name': 'Haitian Creole'}, {'language': 'ha', 'name': 'Hausa'}, {'language': 'haw', 'name': 'Hawaiian'}, {'language': 'iw', 'name': 'Hebrew'}, {'language': 'hi', 'name': 'Hindi'}, {'language': 'hmn', 'name': 'Hmong'}, {'language': 'hu', 'name': 'Hungarian'}, {'language': 'is', 'name': 'Icelandic'}, {'language': 'ig', 'name': 'Igbo'}, {'language': 'id', 'name': 'Indonesian'}, {'language': 'ga', 'name': 'Irish'}, {'language': 'it', 'name': 'Italian'}, {'language': 'ja', 'name': 'Japanese'}, {'language': 'jw', 'name': 'Javanese'}, {'language': 'kn', 'name': 'Kannada'}, {'language': 'kk', 'name': 'Kazakh'}, {'language': 'km', 'name': 'Khmer'}, {'language': 'rw', 'name': 'Kinyarwanda'}, {'language': 'ko', 'name': 'Korean'}, {'language': 'ku', 'name': 'Kurdish (Kurmanji)'}, {'language': 'ky', 'name': 'Kyrgyz'}, {'language': 'lo', 'name': 'Lao'}, {'language': 'la', 'name': 'Latin'}, {'language': 'lv', 'name': 'Latvian'}, {'language': 'lt', 'name': 'Lithuanian'}, {'language': 'lb', 'name': 'Luxembourgish'}, {'language': 'mk', 'name': 'Macedonian'}, {'language': 'mg', 'name': 'Malagasy'}, {'language': 'ms', 'name': 'Malay'}, {'language': 'ml', 'name': 'Malayalam'}, {'language': 'mt', 'name': 'Maltese'}, {'language': 'mi', 'name': 'Maori'}, {'language': 'mr', 'name': 'Marathi'}, {'language': 'mn', 'name': 'Mongolian'}, {'language': 'my', 'name': 'Myanmar (Burmese)'}, {'language': 'ne', 'name': 'Nepali'}, {'language': 'no', 'name': 'Norwegian'}, {'language': 'or', 'name': 'Odia (Oriya)'}, {'language': 'ps', 'name': 'Pashto'}, {'language': 'fa', 'name': 'Persian'}, {'language': 'pl', 'name': 'Polish'}, {'language': 'pt', 'name': 'Portuguese'}, {'language': 'pa', 'name': 'Punjabi'}, {'language': 'ro', 'name': 'Romanian'}, {'language': 'ru', 'name': 'Russian'}, {'language': 'sm', 'name': 'Samoan'}, {'language': 'gd', 'name': 'Scots Gaelic'}, {'language': 'sr', 'name': 'Serbian'}, {'language': 'st', 'name': 'Sesotho'}, {'language': 'sn', 'name': 'Shona'}, {'language': 'sd', 'name': 'Sindhi'}, {'language': 'si', 'name': 'Sinhala'}, {'language': 'sk', 'name': 'Slovak'}, {'language': 'sl', 'name': 'Slovenian'}, {'language': 'so', 'name': 'Somali'}, {'language': 'es', 'name': 'Spanish'}, {'language': 'su', 'name': 'Sundanese'}, {'language': 'sw', 'name': 'Swahili'}, {'language': 'sv', 'name': 'Swedish'}, {'language': 'tg', 'name': 'Tajik'}, {'language': 'ta', 'name': 'Tamil'}, {'language': 'tt', 'name': 'Tatar'}, {'language': 'te', 'name': 'Telugu'}, {'language': 'th', 'name': 'Thai'}, {'language': 'tr', 'name': 'Turkish'}, {'language': 'tk', 'name': 'Turkmen'}, {'language': 'uk', 'name': 'Ukrainian'}, {'language': 'ur', 'name': 'Urdu'}, {'language': 'ug', 'name': 'Uyghur'}, {'language': 'uz', 'name': 'Uzbek'}, {'language': 'vi', 'name': 'Vietnamese'}, {'language': 'cy', 'name': 'Welsh'}, {'language': 'xh', 'name': 'Xhosa'}, {'language': 'yi', 'name': 'Yiddish'}, {'language': 'yo', 'name': 'Yoruba'}, {'language': 'zu', 'name': 'Zulu'}, {'language': 'he', 'name': 'Hebrew'}, {'language': 'zh', 'name': 'Chinese (Simplified)'}]
    
    def __init__(self,apikey: str,
                      credentials: str,
                      db: sqlitedb):
        if not os.path.exists(credentials):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), credentials)
            
        if not os.path.exists(apikey):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), apikey)
            
        with open(apikey, "r") as f:
            apikey = f.readline().strip()
        
        self.translatecache = Gapi._TranslateCache(db)
        
        # init gapi clients
        #os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials
        self.annotator = vision.ImageAnnotatorClient.from_service_account_json(credentials)
        self.translator = translate.Client.from_service_account_json(credentials)
        self.gmaps = googlemaps.Client(key=apikey)
        
    @staticmethod
    def check_credentials(credentials:str):
        try:
            annotator = vision.ImageAnnotatorClient.from_service_account_json(credentials)
            rootpath = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(rootpath, 'web','favicon.ico'), 'rb') as image_file:
                content = image_file.read()
            annotator.label_detection(image=vision.Image(content=content))
        except:
            return False
            
        try:
            translator = translate.Client.from_service_account_json(credentials)
            translator.translate('Hello World')
            return True
        except:
            return False
    
    @staticmethod
    def check_apikey(apikey:str):
        try:
            with open(apikey, "r") as f:
                apikey = f.readline().strip()
            gmaps = googlemaps.Client(key=apikey)
            gmaps.reverse_geocode((0,0))
            return True
        except:
            return False
        
        
    def translate(self,text: str,
                       target_language: str='en'):
        if not text in self.translatecache[target_language]:
            result = self.translator.translate(text,target_language=target_language)["translatedText"]
            self.translatecache[target_language][text] = result
        return self.translatecache[target_language][text]
    
    def getlocation(self,latlon:Tuple[float,float],target_language='en'):
        self.lookup = self.gmaps.reverse_geocode(latlon)
        
        location = [self.translate(comp['long_name'],target_language) for comp in self.lookup[0]['address_components'] if 'locality' in comp['types'] or 'country' in comp['types'] ]
        if (len(location) == 1):
            location.extend([self.translate(comp['long_name'],target_language) for comp in self.lookup[0]['address_components'] if 'administrative_area_level_2' in comp['types']])
        
        try:
            # Also use Nominatim API and fuse results
            location2 = self.geolocator.reverse(latlon,exactly_one=True, timeout=10, addressdetails=True)
            location.extend([self.translate(location2.raw['address'][field],target_language) for field in ['suburb','city','state','town','country','locality'] if field in location2.raw['address']])
        except:
            pass
        return list(set(location))
    
    def annotate(self,imagecontent: bytes,
                      vision_features: dict=VISION_FEATURES,
                      target_language: str='en'):
        image = vision.Image(content=imagecontent)
        self.response = self.annotator.annotate_image({
							'image': image,
							'features': [{'type_': feature,'max_results':40} for feature in vision_features if feature in Gapi.VISION_FEATURES],
						},timeout=10.0)
        labels = []
        # label annotations
        if 'LABEL_DETECTION' in vision_features:
            labels.extend([self.translate(label.description,target_language) for label in self.response.label_annotations if label.score >= vision_features['LABEL_DETECTION']])
        # object annotations
        if 'OBJECT_LOCALIZATION' in vision_features:
            labels.extend([self.translate(obj.name,target_language) for obj in self.response.localized_object_annotations if obj.score >= vision_features['OBJECT_LOCALIZATION']])
        # landmark annotations
        if 'LANDMARK_DETECTION' in vision_features:
            labels.extend([self.translate(landmark.description,target_language) for landmark in self.response.landmark_annotations if landmark.score >= vision_features['LANDMARK_DETECTION']])
        # logo annotations
        if 'LOGO_DETECTION' in vision_features:
            labels.extend([self.translate(logo.description,target_language) for logo in self.response.logo_annotations if logo.score >= vision_features['LOGO_DETECTION']])
        # text detection
        if 'TEXT_DETECTION' in vision_features:
            # the first annotation is the complete text, all further are the single words
            if self.response.text_annotations and self.response.text_annotations[0].score >= vision_features['TEXT_DETECTION']:
                labels.append(self.response.text_annotations[0].description.replace('\n',' ').replace(';',' ').replace(',',' '))
        # image properties
        if 'IMAGE_PROPERTIES' in vision_features:
            color_names = [rgb_to_name((color.color.red,color.color.green,color.color.blue)) for color in self.response.image_properties_annotation.dominant_colors.colors if color.pixel_fraction >= vision_features['IMAGE_PROPERTIES']]
            labels.extend([self.translate(color,target_language) for colorlist in color_names for color in colorlist])
        # face tags
        faces = []
        if 'FACE_DETECTION' in vision_features:
            faces.extend([[(vertex.x, vertex.y) for vertex in face.bounding_poly.vertices] for face in self.response.face_annotations if face.detection_confidence >= vision_features['FACE_DETECTION']])
                
        return (list(set(labels)),faces)
    
    class _TranslateCache:
        def __init__(self,db: sqlitedb):
            self._db = db
            self._translatecaches = {}
    
        def _get_cache(self,target_language: str):
            if not target_language in self._translatecaches:
                self._translatecaches[target_language] = Gapi._TranslateCache._Language(self._db, target_language)
            return self._translatecaches[target_language]
        
        def __getattr__(self,key: str):
            if key.startswith('_'):
                return super(Gapi._TranslateCache, self).__getattr__(key)
            else:
                return self._get_cache(str(key))
                
        def __getitem__(self,key:str): return self._get_cache(str(key))
        
        class _Language:
            def __init__(self,db:sqlitedb,
                              target_language:str):
                self._db = db
                self._target_language = target_language
                self._checkTable()
            
            def _checkTable(self):
                self._db.execute(f"""CREATE TABLE IF NOT EXISTS translation(
                    id INTEGER PRIMARY KEY,
                    source TEXT NOT NULL UNIQUE,
                    {self._target_language} TEXT);""",True)
                
                # check if translation column exists
                lang_exists = bool(self._db.execute(f"SELECT COUNT(*) AS CNTREC FROM pragma_table_info('translation') WHERE name='{self._target_language}';").fetchone()[0])
                if (not lang_exists):
                    self._db.execute(f"ALTER TABLE translation ADD {self._target_language} TEXT;",True)
                    
                self._translatecache = {key : value for (key,value) in self._db.execute(f"SELECT source, {self._target_language} FROM translation WHERE {self._target_language} IS NOT NULL;").fetchall()}
        
            def _get_cache(self,key:str):
                return self._translatecache[key]
                
            def _set_cache(self,key:str,value:str):
                if not key in self._translatecache:
                    self._translatecache[key] = value
                    esc_key = key.replace("'", "''")
                    esc_value = value.replace("'", "''")
                    try:
                        self._db.execute(f"INSERT INTO translation (source, {self._target_language}) VALUES ('{esc_key}','{esc_value}');",True)
                    except:
                        self._db.execute(f"UPDATE translation SET {self._target_language} = '{esc_value}' WHERE source = '{esc_key}';",True)
            
            def __getattr__(self,key:str):
                if key.startswith('_'):
                    return super(Gapi._TranslateCache._Language, self).__getattr__(key)
                else:
                    return self._get_cache(str(key))
                
            def __setattr__(self,key:str,value:str):
                if key.startswith('_'):
                    super(Gapi._TranslateCache._Language, self).__setattr__(key, value)
                else:
                    self._set_cache(str(key), value)
                    
            def __getitem__(self,key:str): return self._get_cache(str(key))
            def __setitem__(self,key:str,value:str): self._set_cache(str(key), value)
            def __contains__(self, item:str): return item in self._translatecache
            def __iter__(self): return iter(self._translatecache)
            def to_dict(self): return self._translatecache
            def copy(self): return self._translatecache.copy()
            def keys(self): return self._translatecache.keys()
            def values(self): return self._translatecache.values()
            def items(self): return self._translatecache.items()