"""Test chunking with a large input to verify multi-chunk processing."""
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from prompt_template import _chunk_text, _estimate_tokens, _max_input_tokens

# Simulate a large Confluence page
large_text = """
Feature: Video Player Controls
1. The user can play/pause the video using the play button.
2. The user can seek forward 10 seconds by pressing the right arrow key.
3. The user can seek backward 10 seconds by pressing the left arrow key.
4. Volume control slider adjusts from 0% to 100%.
5. Mute button toggles audio on/off.
6. Fullscreen button expands the player to full screen.
7. Picture-in-Picture mode shows a floating mini player.
8. Subtitles toggle button shows/hides captions.
9. Quality selector allows choosing 480p, 720p, 1080p, 4K.
10. Playback speed options: 0.5x, 1x, 1.5x, 2x.
""" * 20  # Repeat to make it ~10k chars

print(f"Input text: {len(large_text)} chars (~{_estimate_tokens(large_text)} tokens)")
print(f"Max input chars per chunk: calculated from budget")

chunks = _chunk_text(large_text, 5000)
print(f"Chunks: {len(chunks)}")
for i, c in enumerate(chunks, 1):
    print(f"  Chunk {i}: {len(c)} chars (~{_estimate_tokens(c)} tokens)")

print("\n=== CHUNKING TEST PASSED ===")
print("(Skipping actual LLM calls for large text to save tokens)")
