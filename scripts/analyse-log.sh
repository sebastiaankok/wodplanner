#!/bin/bash

kubectl logs deployments/wodplanner| grep 'api.client' | awk '{print $5}' | tr -d '()' | sort | uniq -c

