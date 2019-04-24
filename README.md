# pg-solve-path-bot

## Description
This is a simple bot that asks for solve paths on /r/PictureGame. Whenever an user posts a new round, the bot will reply with a question and an username mention on the previous round in the format `How did you find the answer /u/redditUsername ?`

## Main principles
- Any action is initiated only after detecting a new round submission from the PRAW stream
- The bot posts a new reply, does audit of its previous comments and checks its inbox for commands
- If a player doesn't reply the bot within 30 minutes, the bot marks the player in the playerDB.json file.
- The bot deletes its comment too if nobody has replied it within 30 minutes
- 30 minutes is the minimum time before any action taken. In practice it will be 30 minutes + the time until a new round gets posted.
- If the round winner doesn't reply 3 times in a row, the bot will stop pinging the player entirely
- If the player hasn't replied only once or twice, but eventually comments on the second or the third mention, then the player will be removed entirely from the playerDB and the counter resets
- The bot doesn't differentiate between who answers to it. The counter gets reset even if someone else than winner responds to it.
- If the player messages the bot with "pingmeagain" in the message body, the player will be removed from the playerDB and the bot will ping them again
