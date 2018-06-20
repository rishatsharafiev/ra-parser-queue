# rds parser container

### Build image
```
docker build --no-cache ./rds/ -t fcmotode/rds:latest
```

### Push to docker hub
```
docker login # if not logged in yet
docker push fcmotode/rds:latest
```

### Run image
```
docker run -p 9001:9001 -v $(pwd)/app:/app -v /var/log:/var/log/supervisor -v /var/log:/var/log/app fcmotode/rds:latest
```