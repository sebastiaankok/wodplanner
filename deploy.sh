#!/usr/bin/env bash
set -euo pipefail

IMAGE="ghcr.io/sebastiaankok/wodplanner"
TAG="${1:-main}"

docker build --platform linux/amd64 -t "${IMAGE}:${TAG}" .
docker push "${IMAGE}:${TAG}"

kubectl --kubeconfig ~/.kube/configs/k3s.yaml --context k3s-home \
  rollout restart deploy -n wodplanner
