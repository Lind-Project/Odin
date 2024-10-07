FROM python:3

WORKDIR /usr/src/app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

RUN addgroup --gid 999 dockerhost && \
    usermod --append --groups 999 root && \
    sg dockerhost -c 'newgrp dockerhost'

CMD [ "python", "odin.py" ]
