FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHON_VERSION 3.10.12

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y libavdevice-dev libavfilter-dev libopus-dev libvpx-dev pkg-config wget
RUN wget -c https://www.python.org/ftp/python/${PYTHON_VERSION%%[a-z]*}/Python-$PYTHON_VERSION.tar.xz
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    curl \
    llvm \
    libncurses5-dev \
    libncursesw5-dev \
    xz-utils \
    tk-dev
RUN tar -xf Python-$PYTHON_VERSION.tar.xz && \
    cd Python-$PYTHON_VERSION && \
    ./configure --enable-optimizations && \
    make -j $(nproc) && \
    make install
RUN rm -r Python-$PYTHON_VERSION.tar.xz Python-$PYTHON_VERSION

RUN apt-get install -y python3-pip

RUN python3 --version
RUN pip3 --version

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

# Install react front
# RUN chmod +x pull.sh
# RUN ./pull.sh

EXPOSE 5000
#EXPOSE 50000-50100/udp

ENV FFMPEG_LOG_LEVEL=error

CMD [ "python3", "./main.py" ]


# FROM python:3.10-slim-bullseye

# WORKDIR /usr/src/app

# # RUN apt-key adv --keyserver keyserver.ubuntu.com --recv-keys F8D2585B8783D481 0E98404D386FA1D9 6ED0E7B82643E131 54404762BBB6E853 BDE6D2B9216EC7A8
# RUN apt-get update && apt-get install -y libavdevice-dev libavfilter-dev libopus-dev libvpx-dev pkg-config wget

# COPY requirements.txt ./
# RUN pip install --no-cache-dir -r requirements.txt

# COPY . .

# RUN wget https://github.com/serengil/deepface_models/releases/download/v1.0/vgg_face_weights.h5
# RUN mkdir -p dirname /root/.deepface/weights/vgg_face_weights.h5 
# RUN mv vgg_face_weights.h5 /root/.deepface/weights/vgg_face_weights.h5

# # Install react front
# RUN chmod +x pull.sh
# RUN ./pull.sh

# EXPOSE 5000
# EXPOSE 50000-50100/udp

# ENV FFMPEG_LOG_LEVEL=error

# CMD [ "python", "./main.py" ]