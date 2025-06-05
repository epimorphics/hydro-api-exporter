.PHONY:	default image publish run tag vars

ACCOUNT?=$(shell aws sts get-caller-identity | jq -r .Account)
REPO=${ACCOUNT}.dkr.ecr.eu-west-1.amazonaws.com
STORE=epimorphics
NAME=hydro-api-exporter
TAG?= $(shell git describe --tags `git rev-list --tags --max-count=1`)
IMAGE?=${STORE}/${NAME}:${TAG}

default: image
all: publish

clean:
	@-docker stop ${NAME} 2> /dev/null
	@-docekr rm ${NAME} 2> /dev/null
	@-docker rmi -f ${REPO}/${IMAGE} ${IMAGE}
	@docker image prune -f

image:
	@docker build --tag ${IMAGE} .
	
publish: image
	@docker tag ${IMAGE} ${REPO}/${IMAGE}
	@docker push ${REPO}/${IMAGE}

run:
	@-docker stop ${NAME} 2> /dev/null
	@-docker rm ${NAME} 2> /dev/null
	@docker run -p 9898:9898 --name ${NAME} ${IMAGE}

tag:
	@echo ${TAG}

vars:
	@echo ACCOUNT:${ACCOUNT}
	@echo TAG:${TAG}
	@echo NAME:${NAME}
	@echo IMAGE:${IMAGE}
