#!/usr/bin/env python3
"""
Generate Twitter Screenshot with Meme

This script generates a Twitter screenshot using a random meme
from the static/memes folder to demonstrate the functionality.
"""

import os
import random
from datetime import datetime, timezone, timedelta
from twitter_screenshot_generator import TwitterScreenshotGenerator
from config_manager import ConfigManager

def get_random_meme():
    """Get a random meme from the static/memes folder."""
    meme_dir = "static/memes"
    if not os.path.exists(meme_dir):
        print(f"❌ Meme directory not found: {meme_dir}")
        return None
    
    memes = [f for f in os.listdir(meme_dir) 
             if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    
    if not memes:
        print("❌ No meme images found")
        return None
    
    selected_meme = random.choice(memes)
    return os.path.join(meme_dir, selected_meme)

def create_bitcoin_tweet_with_meme():
    """Create a realistic Bitcoin tweet with a meme attached."""
    
    # Get a random meme
    meme_path = get_random_meme()
    if not meme_path:
        return None
    
    # Bitcoin-themed tweet content options
    tweet_options = [
        {
            'text': "Just HODL! 💎🙌 Bitcoin is the future of money. This meme perfectly captures how I feel about the current market. #Bitcoin #HODL #DiamondHands #BTC #Cryptocurrency",
            'author': 'Bitcoin HODLER',
            'username': 'btcmaxi'
        },
        {
            'text': "When people ask me about Bitcoin volatility, I show them this. 😂 Remember: zoom out! We're still early in this game. #Bitcoin #Memes #BTC #CryptoMemes",
            'author': 'Crypto Comedian',
            'username': 'cryptomemes'
        },
        {
            'text': "This meme explains Bitcoin better than any whitepaper! 🚀 Sometimes humor is the best way to understand complex technology. #Bitcoin #Education #Memes",
            'author': 'Satoshi Fan',
            'username': 'satoshifan21'
        },
        {
            'text': "Found this gem and had to share! 😄 The Bitcoin community has the best memes. Who else can relate? #BitcoinMemes #BTC #CryptoHumor #MemeCoin",
            'author': 'Meme Master',
            'username': 'mememaster'
        },
        {
            'text': "Me explaining Bitcoin to my family at dinner... 🤣 Why is it always so hard to explain magic internet money? Share if you can relate! #Bitcoin #Family #Memes",
            'author': 'Bitcoin Educator',
            'username': 'btceducator'
        }
    ]
    
    # Select random tweet template
    selected_tweet = random.choice(tweet_options)
    
    # Create timestamp (random time in last 6 hours)
    now = datetime.now(timezone.utc)
    random_hours = random.uniform(0.5, 6.0)
    created_at = now - timedelta(hours=random_hours)
    
    # Build tweet data
    tweet_data = {
        'text': selected_tweet['text'],
        'author_name': selected_tweet['author'],
        'author_username': selected_tweet['username'],
        'created_at': created_at.isoformat(),
        'id': f"demo_tweet_{random.randint(100000, 999999)}",
        'image_url': f"file://{os.path.abspath(meme_path)}"
    }
    
    print(f"📝 Tweet content: {tweet_data['text'][:80]}...")
    print(f"👤 Author: {tweet_data['author_name']} (@{tweet_data['author_username']})")
    print(f"🖼️  Meme: {os.path.basename(meme_path)}")
    
    return tweet_data

def generate_twitter_screenshot():
    """Generate a Twitter screenshot with meme."""
    print("🐦 Twitter Screenshot Generator with Meme")
    print("=" * 50)
    
    try:
        # Load configuration
        config_manager = ConfigManager("config.json")
        config = config_manager.get_current_config()
        
        # Initialize screenshot generator
        generator = TwitterScreenshotGenerator(config)
        print(f"📁 Output directory: {generator.output_dir}")
        
        # Create tweet data with meme
        print("\n📋 Creating tweet data...")
        tweet_data = create_bitcoin_tweet_with_meme()
        
        if not tweet_data:
            print("❌ Failed to create tweet data")
            return None
        
        # Generate screenshot
        print(f"\n🎨 Generating screenshot...")
        screenshot_path = generator.generate_screenshot(tweet_data)
        
        if screenshot_path:
            print(f"\n✅ Success! Screenshot generated:")
            print(f"📁 File: {screenshot_path}")
            
            # Get file info
            if os.path.exists(screenshot_path):
                file_size = os.path.getsize(screenshot_path)
                print(f"📊 Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
            
            print(f"\n🎯 Features demonstrated:")
            print(f"   • Twitter-style layout with avatar, username, handle")
            print(f"   • Proper text wrapping and formatting")
            print(f"   • Meme image embedded and scaled appropriately")
            print(f"   • Realistic timestamp formatting")
            print(f"   • Fixed text alignment (no overlap with avatar)")
            
            return screenshot_path
        else:
            print("❌ Screenshot generation failed")
            return None
            
    except Exception as e:
        print(f"❌ Error generating screenshot: {e}")
        import traceback
        traceback.print_exc()
        return None

def show_available_memes():
    """Show what memes are available."""
    print("\n📁 Available memes in static/memes:")
    meme_dir = "static/memes"
    
    if os.path.exists(meme_dir):
        memes = [f for f in os.listdir(meme_dir) 
                 if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        
        if memes:
            print(f"Found {len(memes)} meme images:")
            for i, meme in enumerate(sorted(memes)[:10], 1):  # Show first 10
                print(f"   {i:2d}. {meme}")
            
            if len(memes) > 10:
                print(f"   ... and {len(memes) - 10} more")
        else:
            print("   No meme images found")
    else:
        print(f"   Directory not found: {meme_dir}")

if __name__ == "__main__":
    # Show available memes
    show_available_memes()
    
    # Generate screenshot
    screenshot_path = generate_twitter_screenshot()
    
    if screenshot_path:
        print(f"\n🎉 Demo completed successfully!")
        print(f"Check the screenshot at: {screenshot_path}")
    else:
        print(f"\n💔 Demo failed. Check error messages above.")
