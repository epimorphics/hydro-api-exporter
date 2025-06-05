.PHONY:	default image publish run tag vars

ACCOUNT?=$(shell aws sts get-caller-identity | jq -r .Account)
REPO=${ACCOUNT}.dkr.ecr.eu-west-1.amazonaws.com
STORE=epimorphics
IMAGE?=${STORE}/${NAME}:${TAG}
NAME=hydro-api-exporter

COMMIT=$(shell git rev-parse --short HEAD)
VERSION?=$(shell git describe --tags `git rev-list --tags --max-count=1`)
TAG?=$(shell printf '%s-%s-%08d' ${VERSION} ${COMMIT} ${GITHUB_RUN_NUMBER})

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
	@echo COMMIT:${COMMIT}
	@echo NAME:${NAME}
	@echo IMAGE:${IMAGE}
	@echo TAG:${TAG}
	@echo VERSION:${VERSION}
