#!/bin/bash
# EKS Live Cost Estimator
# Estimates running costs based on cluster uptime
# Requires: aws CLI, jq, bc

CLUSTER_NAME="ray-llm-demo"  # Change if needed
REGION="us-east-1"

# Rates (update based on your instance type and Spot pricing)
CONTROL_PLANE_RATE=0.10   # $ per hour (standard EKS fee)
GPU_SPOT_RATE=0.45        # Average g5.xlarge Spot in us-east-1 (check current with aws ec2 describe-spot-price-history)

# Get cluster creation time
CREATION_TIME=$(aws eks describe-cluster --name $CLUSTER_NAME --region $REGION --query 'cluster.createdAt' --output text 2>/dev/null)

if [ -z "$CREATION_TIME" ]; then
  echo "Cluster $CLUSTER_NAME not found or not accessible."
  exit 1
fi

START_EPOCH=$(date -d "$CREATION_TIME" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S.%NZ" "$CREATION_TIME" +%s)
NOW_EPOCH=$(date +%s)
HOURS_RUNNING=$(echo "($NOW_EPOCH - $START_EPOCH) / 3600" | bc -l)

CONTROL_COST=$(echo "$HOURS_RUNNING * $CONTROL_PLANE_RATE" | bc -l)
GPU_COST=$(echo "$HOURS_RUNNING * $GPU_SPOT_RATE" | bc -l)
TOTAL=$(echo "$CONTROL_COST + $GPU_COST" | bc -l)

echo "=================================="
echo "EKS Cluster: $CLUSTER_NAME"
echo "Running for: $(printf "%.2f" $HOURS_RUNNING) hours"
echo "----------------------------------"
echo "Control plane:  \$$  (printf "%.3f" $CONTROL_COST)"
echo "GPU node (Spot): \  $$(printf "%.3f" $GPU_COST)"
echo "Estimated total: \$$(printf "%.3f" $TOTAL)"
echo "=================================="
echo "Note: Actual Spot price may vary. Check with:"
echo "aws ec2 describe-spot-price-history --instance-types g5.xlarge --product-descriptions "Linux/UNIX" --region $REGION"
