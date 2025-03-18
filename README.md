**Запуск приложения из корневой директории проекта**
1. Соберите Docker-образ:

`sudo docker build --no-cache -t megaplan-nextcloud .`

2. Запустите Docker-контейнер:

_для linux:_
`sudo docker run -d --name megaplan-container --restart=always -v $(pwd)/logs:/app/logs -p 8000:8000 megaplan-nextcloud`

_для windows:_
`docker run -d --name megaplan-container --restart=always -v ${PWD}/logs:/app/logs -p 8000:8000 megaplan-nextcloud`

**_Если нужно удалить контейнер для перезапуска кода:_**
`sudo docker rm -f megaplan-container`