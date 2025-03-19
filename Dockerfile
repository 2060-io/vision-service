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

EXPOSE 5000

ENV FFMPEG_LOG_LEVEL=error

CMD [ "python3", "./main.py" ]