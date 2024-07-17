#!/bin/bash
cat > "/tmp/mergefilter.txt" <<-EOH
	- venv
	- copy-to-server.sh
	- InviteBot.txt
	- __pycache__
	- runtime.log
	- gitignore
	- .env.template
	- .git
	- crontab-entry.txt
	- Clubbot.service
	- .env.prod
	- .env.dev
EOH

rsync -avzu --delete --progress -h --filter="merge /tmp/mergefilter.txt" ./ japan:/home/mildnfab/clubbot
rsync -avzu --delete --progress -h ./Clubbot.service japan:/home/mildnfab/.config/systemd/user/Clubbot.service
