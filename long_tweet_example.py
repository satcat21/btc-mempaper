#!/usr/bin/env python3
"""
Generate Long Twitter Screenshot Example
"""

import os
import random
from datetime import datetime, timezone, timedelta
from twitter_screenshot_generator import TwitterScreenshotGenerator
from config_manager import ConfigManager

def create_long_tweet_example():
    print('🎨 Generating long Twitter screenshot example...')

    # Load config
    config = ConfigManager('config.json').get_current_config()
    generator = TwitterScreenshotGenerator(config)

    # Get random meme
    meme_dir = 'static/memes'
    memes = [f for f in os.listdir(meme_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    meme_path = os.path.join(meme_dir, random.choice(memes))

    # Create a longer tweet
    long_tweet = {
        'text': """🚨 BREAKING: Bitcoin just reached a new milestone! 

Here's why this matters for the future of decentralized finance:

• Institutional adoption is accelerating
• More countries are considering Bitcoin legal tender  
• Lightning Network transactions are growing exponentially
• Self-custody solutions are becoming mainstream

The revolution is not televised - it's happening on the blockchain! 

This meme perfectly captures how we all feel right now 😂

#Bitcoin #BTC #Cryptocurrency #DeFi #LightningNetwork #HODL #DiamondHands""",
        'author_name': 'Bitcoin News Network',
        'author_username': 'btcnews',
        'created_at': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        'id': 'demo_long_tweet_123',
        'image_url': f'file://{os.path.abspath(meme_path)}'
    }

    print(f'📝 Creating long tweet with meme: {os.path.basename(meme_path)}')
    print(f'👤 Author: {long_tweet["author_name"]} (@{long_tweet["author_username"]})')

    # Generate screenshot
    screenshot_path = generator.generate_screenshot(long_tweet)

    if screenshot_path:
        file_size = os.path.getsize(screenshot_path)
        print(f'✅ Long tweet screenshot generated!')
        print(f'📁 File: {screenshot_path}')
        print(f'📊 Size: {file_size:,} bytes ({file_size/1024:.1f} KB)')
        return screenshot_path
    else:
        print('❌ Failed to generate screenshot')
        return None

if __name__ == "__main__":
    create_long_tweet_example()
