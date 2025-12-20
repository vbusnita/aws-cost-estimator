#!/bin/bash
# Live EKS Cost Watcher
# Watches costs in real-time while your cluster runs
# Requires: aws CLI, jq, bc

CLUSTER_NAME="ray-llm-demo"
REGION="us-east-1"

# Fixed EKS control plane rate
CONTROL_PLANE_RATE=0.10  # $ per hour

echo "Starting live cost watcher for EKS cluster: $CLUSTER_NAME"
echo "Press Ctrl+C to stop"
echo ""

while true; do
  clear
  echo "========================================"
  echo "   LIVE EKS COST ESTIMATOR"
  echo "   Cluster: $CLUSTER_NAME | Region: $REGION"
  echo "========================================"
  echo ""

  # Check if cluster exists
  if ! aws eks describe-cluster --name $CLUSTER_NAME --region $REGION > /dev/null 2>&1; then
    echo "❌ Cluster not found or not accessible."
    echo "   Waiting for cluster to be created..."
    sleep 30
    continue
  fi

   # Get cluster creation time
  CREATION_TIME=$(aws eks describe-cluster --name $CLUSTER_NAME --region $REGION --query 'cluster.createdAt' --output text)

  # Use Python to parse the ISO timestamp to epoch (handles nanoseconds and timezone perfectly)
  START_EPOCH=$(python3 -c "import datetime, sys; dt = datetime.datetime.fromisoformat(sys.argv[1]); print(int(dt.timestamp()))" "$CREATION_TIME" 2>/dev/null)

  if [ -z "$START_EPOCH" ] || [ "$START_EPOCH" = "None" ]; then
    echo "⚠️  Failed to parse creation time with Python"
    HOURS_RUNNING=0
  else
    NOW_EPOCH=$(date +%s)
    HOURS_RUNNING=$(echo "($NOW_EPOCH - $START_EPOCH) / 3600" | bc -l)
  fi

  CONTROL_COST=$(echo "$HOURS_RUNNING * $CONTROL_PLANE_RATE" | bc -l)

  # Fetch current Spot price for g5.xlarge (Linux/UNIX in us-east-1)
  SPOT_PRICE=$(aws ec2 describe-spot-price-history \
    --instance-types g5.xlarge \
    --product-descriptions "Linux/UNIX" \
    --region $REGION \
    --max-items 1 \
    --query 'SpotPriceHistory[0].SpotPrice' \
    --output text 2>/dev/null || echo "0.45")

  GPU_COST=$(echo "$HOURS_RUNNING * $SPOT_PRICE" | bc -l)
  TOTAL=$(echo "$CONTROL_COST + $GPU_COST" | bc -l)

  echo "⏱  Running for: $(printf "%.3f" $HOURS_RUNNING) hours"
  echo ""
  echo "💰 Current Spot price (g5.xlarge): \$$SPOT_PRICE/hour"
  echo ""
  echo "📊 Estimated costs so far:"
  echo "   • Control plane:     \$$(printf "%.4f" $CONTROL_COST)"
  echo "   • GPU node (Spot):   \$$(printf "%.4f" $GPU_COST)"
  echo "   • Total:             \$$(printf "%.4f" $TOTAL)"
  echo ""
  echo "🔄 Updates every 30 seconds | $(date)"
  echo ""
  echo "Note: Spot price fluctuates. Destroy cluster when done to stop costs!"

  sleep 30
done
