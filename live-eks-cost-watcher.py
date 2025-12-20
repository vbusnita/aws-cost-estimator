#!/usr/bin/env python3
import subprocess
import datetime
import time
import curses
import sys
from typing import Tuple

CLUSTER_NAME = "ray-llm-demo"
REGION = "us-east-1"
CONTROL_PLANE_RATE = 0.10  # $/hour
UPDATE_INTERVAL = 30  # seconds

def get_cluster_creation_time() -> str:
    """Get cluster createdAt from AWS CLI"""
    try:
        result = subprocess.run([
            'aws', 'eks', 'describe-cluster', '--name', CLUSTER_NAME, 
            '--region', REGION, '--query', 'cluster.createdAt', 
            '--output', 'text'
        ], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def get_spot_price() -> float:
    """Get current g5.xlarge Spot price"""
    try:
        result = subprocess.run([
            'aws', 'ec2', 'describe-spot-price-history',
            '--instance-types', 'g5.xlarge',
            '--product-descriptions', 'Linux/UNIX',
            '--region', REGION, '--max-items', '1',
            '--query', 'SpotPriceHistory[0].SpotPrice', '--output', 'text'
        ], capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0.45  # fallback

def main(stdscr):
    curses.curs_set(0)  # Hide cursor
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Green
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK) # Yellow
    curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)    # Red

    stdscr.timeout(100)  # Non-blocking input

    try:
        while True:
            stdscr.clear()
            
            # Header
            stdscr.addstr(0, 0, "═" * 50, curses.A_BOLD)
            stdscr.addstr(1, 0, f" LIVE EKS COST ESTIMATOR ", curses.A_BOLD | curses.color_pair(1))
            stdscr.addstr(2, 0, f" Cluster: {CLUSTER_NAME} | Region: {REGION} ", curses.A_BOLD)
            stdscr.addstr(3, 0, "═" * 50, curses.A_BOLD)
            
            creation_time = get_cluster_creation_time()
            if not creation_time:
                stdscr.addstr(5, 0, "❌ Cluster not found or inaccessible", curses.color_pair(3))
                stdscr.addstr(6, 0, "   Waiting for cluster creation...", curses.A_BOLD)
                stdscr.refresh()
                time.sleep(UPDATE_INTERVAL)
                continue
            
            # Parse creation time
            try:
                dt = datetime.datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                start_epoch = dt.timestamp()
                now_epoch = time.time()
                hours_running = (now_epoch - start_epoch) / 3600
            except ValueError:
                stdscr.addstr(5, 0, "⚠️  Failed to parse creation time", curses.color_pair(2))
                stdscr.refresh()
                time.sleep(UPDATE_INTERVAL)
                continue
            
            # Costs
            spot_price = get_spot_price()
            control_cost = hours_running * CONTROL_PLANE_RATE
            gpu_cost = hours_running * spot_price
            total_cost = control_cost + gpu_cost
            
            stdscr.addstr(5, 0, f"⏱  Running for: {hours_running:.3f} hours")
            stdscr.addstr(7, 0, f"💰 Spot price (g5.xlarge): ${spot_price:.4f}/hour")
            stdscr.addstr(9, 0, "📊 Estimated costs so far:", curses.A_BOLD)
            stdscr.addstr(10, 2, f"• Control plane:     ${control_cost:.4f}")
            stdscr.addstr(11, 2, f"• GPU node (Spot):   ${gpu_cost:.4f}")
            stdscr.addstr(12, 2, f"• TOTAL:             ${total_cost:.4f}", curses.color_pair(1) | curses.A_BOLD)
            
            stdscr.addstr(14, 0, f"🔄 Last update: {datetime.datetime.now().strftime('%H:%M:%S')} | Ctrl+C to exit")
            stdscr.addstr(15, 0, "⚠️  Destroy cluster when done: terraform destroy")
            
            stdscr.refresh()
            time.sleep(UPDATE_INTERVAL)
            
    except KeyboardInterrupt:
        stdscr.addstr(16, 0, "Exiting...", curses.A_BOLD)
        stdscr.refresh()
        time.sleep(1)

if __name__ == "__main__":
    curses.wrapper(main)