import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'c:\Users\Sambhav\Desktop\Mojo - Copy\mojo_ui.py'
content = open(path, encoding='utf-8').read()

# Curly apostrophe U+2019, right arrow U+2192
old_block = (
    'How to handle the conversation (follow this order):\n'
    '1. User apologises / says close it / my bad \u2192 brief chill reply, [CLOSE_NOW].\n'
    '2. User hasn\u2019t given a reason yet \u2192 casually ask what\u2019s up. End with [DENY_ACCESS] (still deciding).\n'
    '3. User gives a reason \u2192 engage with it. If it sounds real (tired, bathroom, water, quick work thing, mental reset) \u2192 say something like \u201calright how long?\u201d then [DENY_ACCESS] (waiting on duration).\n'
    '4. User gives a duration after a valid reason \u2192 grant it warmly. [GRANT_ACCESS n].\n'
    '5. Reason is weak (bored, nothing, just vibing, vague) \u2192 acknowledge it lightly, then close. [DENY_ACCESS].\n'
    '6. They\u2019re being funny \u2192 laugh a little, redirect, close. [DENY_ACCESS].'
)

new_block = (
    'VALID reasons (earn a break): genuinely tired after real work, bathroom, water/food, urgent message, earned rest after grinding.\n'
    'INVALID (close immediately, no second chance): "just listening to music", "just watching videos", "just chilling", bored, idk, vague, any bare entertainment with no context.\n'
    '\n'
    'How to handle:\n'
    '1. Sorry / close it / my bad \u2192 brief reply, [CLOSE_NOW].\n'
    '2. No reason yet \u2192 ask what\u2019s up. [DENY_ACCESS] as placeholder.\n'
    '3. VALID reason \u2192 ask "how long?", [DENY_ACCESS] while waiting.\n'
    '4. Duration given after valid reason \u2192 [GRANT_ACCESS n].\n'
    '5. INVALID reason (bare music/video/chill excuse) \u2192 short callout, close. [DENY_ACCESS].\n'
    '6. Funny / evasive \u2192 brief laugh, redirect, close. [DENY_ACCESS].'
)

if old_block in content:
    content = content.replace(old_block, new_block, 1)
    open(path, 'w', encoding='utf-8').write(content)
    print('DONE')
else:
    print('NOT FOUND - checking for curly quotes in snippet')
    marker = 'How to handle the conversation (follow this order):'
    idx = content.find(marker)
    snippet = content[idx:idx+500]
    print(repr(snippet))
