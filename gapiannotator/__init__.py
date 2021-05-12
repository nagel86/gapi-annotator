# -*- coding: utf-8 -*-
#
# Copyright (C) 2021, Sebastian Nagel.
#
# This file is part of the module 'gapiannotator' and is released under
# the MIT License: https://opensource.org/licenses/MIT
#

__author__ = "Sebastian Nagel"
__copyright__ = "Copyright 2021, Sebastian Nagel"
__license__ = "MIT"
__version__ = "0.1.0"


import argparse
import os, sys, signal

ROOT = os.getcwd()
PKG_ROOT = os.path.dirname(os.path.abspath(__file__))

def webgui():
    from .annotator import ImageLibrary
    signal.signal(signal.SIGINT, goodbye)
    parser = argparse.ArgumentParser(
        description="Automatic image annotator using Google APIs (Cloud Vision, "
                    "Cloud Translation, and Geocoding) with an integrated face tagger. " 
                    "Fully configurable through a Web GUI.")
    parser.add_argument(
        "-l",
        "--listen",
        default="0.0.0.0",
        help="Specify the IP address on which the web server listens. Defaults to 0.0.0.0",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=8000,
        help="Specify the port on which the web server listens. Defaults to 8000",
    )
    parser.add_argument(
        'path', 
        nargs='?',
        type=os.path.abspath,
        default=os.path.join(ROOT,'annotator.db'),
        help="Path to the sqlite database file (will store all settings and act"
             " as a translation cache). Defaults to ./annotator.db")
    args = parser.parse_args()
    library = ImageLibrary(args.path)
    library.launch_webinterface(args.listen,args.port,blocking = True)
    
def cli():
    from .annotator import ImageLibrary
    from .gapi import Gapi
    signal.signal(signal.SIGINT, goodbye)
    parser = argparse.ArgumentParser(
        description="Automatic image annotator using Google APIs (Cloud Vision, "
                    "Cloud Translation, and Geocoding). This is the command-line interface, "
                    "you can also use the WEB interface for more comfort as well as for "
                    "using the face tagger.")
    parser.add_argument(
        "-d",
        "--database",
        nargs='?',
        type=os.path.abspath,
        default=os.path.join(ROOT,'annotator.db'),
        help="Path to the sqlite database file (will store all settings and act"
             " as a translation cache). Defaults to ./annotator.db",
    )
    parser.add_argument(
        "--vision-features",
        metavar="FEATURE=THRESHOLD",
        nargs='*',
        default=[f'{key}={value}' for (key,value) in Gapi.VISION_FEATURES.items()],
        help="Set a number of feature-threshold pairs. "
             "Threshold has to be in range [0,1]. By default, all features will be enabled. "
             "Possible features: {}".format(", ".join(Gapi.VISION_FEATURES.keys())))
    parser.add_argument(
        "--language",
        type=str,
        default='en',
        help="Labels can be translated to a specified language. "
             "Has to be a ISO 639-1 language code! "
             "Defaults to 'en'"
    )
    parser.add_argument(
        "--reverse-geocoding",
        action='store_true',
        help="If set, location (town, region, country) will be added to the labels, "
             "if the image has a GPS tag.")
    parser.add_argument(
        "--replace-labels",
        action='store_true',
        help="If set, existing labels will be replaced, else new labels will be appended.")
    parser.add_argument(
        "--rotate-images",
        action='store_true',
        help="If set, images will be rotated according to the EXIF orientation tag.")
    parser.add_argument(
        "--reannotate",
        action='store_true',
        help="If set, already annotated images will be annotated again, else they will be skipped.")
    parser.add_argument(
        "--threads",
        default=4,
        type=int,
        help="Number of processing threads. Defaults to 4")
    parser.add_argument(
        "--gapi-key",
        type=os.path.abspath,
        help="Path to a file which stores the Google API key. Must only be set once, "
             "afterwards it will be stored in the database.")
    parser.add_argument(
        "--gapi-credentials",
        type=os.path.abspath,
        help="Path to the Google API credentials file (*.json). Must only be set once, "
             "afterwards it will be stored in the database.")
    parser.add_argument(
        'path', 
        nargs='+',
        type=os.path.abspath,
        default=ROOT,
        help='Paths (folders or files) which will be scanned and annotated.')
    args = parser.parse_args()
    
    library = ImageLibrary(args.database)
    
    if args.gapi_key:
        if Gapi.check_apikey(args.gapi_key):
            library.settings.gapi_key = args.gapi_key
        else:
            print('Invalid Google API key!')
            sys.exit(1)
    else:
        if not library.settings.gapi_key:
            print('You have to specify a Google API key file!')
            sys.exit(1)
            
    if args.gapi_credentials:
        if Gapi.check_credentials(args.gapi_credentials):
            library.settings.gapi_credentials = args.gapi_credentials
        else:
            print('Invalid Google API credentials!')
            sys.exit(1)
    else:
        if not library.settings.gapi_credentials:
            print('You have to specify a Google API credentials file!')
            sys.exit(1)
    
    library.process(paths = args.path,
                    vision_features = parse_visionfeatures(args.vision_features),
                    reverse_geocoding = args.reverse_geocoding,
                    num_threads = max(1,args.threads),
                    translate = args.language,
                    replace_labels = args.replace_labels,
                    rotate_images = args.rotate_images,
                    reannotate = args.reannotate,
                    blocking = True)
    goodbye()
    
def parse_visionfeatures(features):
    from .gapi import Gapi
    feature_dict = {}
    for feature in features:
        
        try:
            (key,value) = feature.split("=")
            key = key.strip()
            value = min(1,max(0,float(value)))
        except:
            print("Invalid vision feature format, has to be FEATURE=THRESHOLD "
                  "which has to be in [0,1]")
            sys.exit(1)
        
        if key in Gapi.VISION_FEATURES:
            feature_dict[key] = value
        else:
            print("Unkown vision-feature '{}', possible: {}".format(key,", ".join(Gapi.VISION_FEATURES.keys())))
            sys.exit(1)
    return feature_dict
    
def goodbye(signal=None,frame=None):
    print('\nGoodbye...')
    sys.exit(0)