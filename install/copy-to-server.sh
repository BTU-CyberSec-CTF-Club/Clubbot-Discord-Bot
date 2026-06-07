#!/bin/bash
cat >"/tmp/mergefilter.txt" <<-EOH
- venv
- install/
- __pycache__
- runtime.log
- gitignore
- .env.template
- .git
- .env
EOH

rsync -avzu --delete --progress -h --filter="merge /tmp/mergefilter.txt" ./ japan:/home/mildnfab/clubbot
rsync -avzu --delete --progress -h ./install/Clubbot.service japan:/home/mildnfab/.config/systemd/user/Clubbot.service
