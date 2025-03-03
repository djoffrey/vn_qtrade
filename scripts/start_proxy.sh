#!/bin/sh
docker run -d --name tinyproxy --restart always -p 127.0.0.1:18888:8888 stilleshan/tinyproxy
