.PHONY:	default image publish run tag vars

ACCOUNT?=$(shell aws sts get-caller-identity | jq -r .Account)
REPO=${ACCOUNT}.dkr.ecr.eu-west-1.amazonaws.com
STORE=epimorphics
IMAGE?=${STORE}/${NAME}:${TAG}
NAME=hydro-api-exporter

EPILOG_VERSION?=v0.0.4

COMMIT=$(shell git rev-parse --short HEAD)
VERSION?=$(shell git describe --tags --abbrev=0)
TAG?=$(shell printf '%s-%s-%08d' ${VERSION} ${COMMIT} ${GITHUB_RUN_NUMBER})

default: image
all: publish

epilog.py:
	@echo "Downloading epilog.py version ${EPILOG_VERSION}"
	@curl --no-progress-meter -L https://github.com/epimorphics/python-epilog/releases/download/${EPILOG_VERSION}/epilog.py > epilog.py

clean:
	@-docker stop ${NAME} 2> /dev/null
	@-docekr rm ${NAME} 2> /dev/null
	@-docker rmi -f ${REPO}/${IMAGE} ${IMAGE}
	@docker image prune -f
	@rm -f epilog.py

image: vars epilog.py
	@docker build --tag ${IMAGE} .
	
publish: image
	@docker tag ${IMAGE} ${REPO}/${IMAGE}
	@docker push ${REPO}/${IMAGE}

run:
	@-docker stop ${NAME} 2> /dev/null
	@-docker rm ${NAME} 2> /dev/null
	@docker run -e DATABASE=$${DATABASE:-hydrology} \
		-e DEBUG=$${DEBUG:-0} \
		-e LOG_LEVEL=$${LOG_LEVEL:-info}\
		-e LOG_FORMAT=$${LOG_FORMAT:-json} \
		-e POSTGRES=$${POSTGRES:-172.17.0.1} \
		-e PASSWORD=$${PASSWORD:-undef} \
		-e PORT=$${PORT:-5432} \
		-e QUEUE=$${QUEUE:-queue} \
		-p 9898:9898 --rm --name ${NAME} ${IMAGE}

tag:
	@echo ${TAG}

vars:
	@echo ACCOUNT:${ACCOUNT}
	@echo COMMIT:${COMMIT}
	@echo NAME:${NAME}
	@echo IMAGE:${IMAGE}
	@echo TAG:${TAG}
	@echo VERSION:${VERSION}
