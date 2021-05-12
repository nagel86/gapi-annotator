FROM python:3.7
MAINTAINER Sebastian Nagel

RUN apt-get update

# Some basic packages
RUN pip install Pillow
RUN pip install numpy
RUN pip install python-dateutil

# py3exiv2 and its dependencies
RUN apt-get install -y exiv2
RUN apt-get install -y libexiv2-dev
RUN apt-get install -y libboost-python-dev
RUN pip install py3exiv2

# jpegtran and its dependencies
RUN apt-get install -y libturbojpeg0-dev
RUN pip install cffi
RUN pip install jpegtran-cffi

# Google API
RUN pip install --upgrade google-cloud-vision
RUN pip install google-cloud-translate==2.0.1
RUN pip install googlemaps

# Recurive version of inotify (INode watcher)
RUN pip install inotifyrecursive

# Packages required for WEB GUI
RUN pip install webcolors
RUN pip install aiohttp
RUN pip install asyncio
RUN pip install libsass

# Copy module files and install it
RUN mkdir -p /gapi-annotator
COPY gapiannotator /gapi-annotator/
COPY check_requirements.sh /gapi-annotator/
COPY README.md /gapi-annotator/
COPY setup.py /gapi-annotator/
RUN pip install /gapi-annotator

# settings/credentials are stored in /data
VOLUME "/data"
WORKDIR "/data"

CMD ["gapi-annotator", "/data/annotator.db"]