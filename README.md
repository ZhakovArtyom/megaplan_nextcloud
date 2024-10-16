**Запуск приложения из корневой директории проекта**
1. Соберите Docker-образ:

`docker build --no-cache -t megaplan-nextcloud .`

2. Запустите Docker-контейнер:

_для linux:_
`docker run -d --name megaplan-container -v $(pwd)/logs:/app/logs -p 8000:8000 megaplan-nextcloud`

_для windows:_
`docker run -d --name megaplan-container -v ${PWD}/logs:/app/logs -p 8000:8000 megaplan-nextcloud`

**_Если нужно удалить контейнер для перезапуска кода:_**
`docker rm -f megaplan-container`