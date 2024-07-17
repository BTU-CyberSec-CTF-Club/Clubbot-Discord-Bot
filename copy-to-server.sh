#!/bin/bash
cat > "/tmp/mergefilter.txt" <<-EOH
	- venv
	- copy-to-server.sh
	- InviteBot.txt
	- __pycache__
	- runtime.log
	- gitignore
	- .env.template
EOH

rsync -avzu --delete --progress -h --filter="merge /tmp/mergefilter.txt" ./ japan:/home/mildnfab/clubbot
