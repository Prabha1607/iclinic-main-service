#!/bin/bash

# -----------------------------
# CONFIGURATION
# -----------------------------
PROJECT_ID="gwx-internship-01"
REGION="us-east1"
SERVICE_NAME="iclinic-main-service"
GAR_REPO="us-east1-docker.pkg.dev/$PROJECT_ID/gwx-gar-intern-01"
IMAGE="$GAR_REPO/iclinic-main-service:latest"
CONN_NAME="$PROJECT_ID:us-east1:gwx-csql-intern-01"

# -----------------------------
# BUILD IMAGE
# -----------------------------
echo "Building Main Service Docker Image..."
docker build -t $IMAGE .

echo "Pushing Docker Image..."
docker push $IMAGE

# -----------------------------
# DEPLOY CLOUD RUN
# -----------------------------
echo "Deploying $SERVICE_NAME..."
gcloud run services update $SERVICE_NAME \
  --image=$IMAGE \
  --region=$REGION \
  --project=$PROJECT_ID \
  --port=8080 \
  --service-account gwx-cloudrun-sa-01@$PROJECT_ID.iam.gserviceaccount.com \
  --add-cloudsql-instances $CONN_NAME \
  --env-vars-file env.yaml

echo "iclinic-main-service deployed successfully!"