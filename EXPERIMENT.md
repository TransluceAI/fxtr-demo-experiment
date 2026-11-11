# Hostility ratings for generated chat messages

Each seeded chat message has two to five sentences after its opening, plus up to five earlier posts
from the same room. The generator chooses a borderline closing remark with probability 75%, an
overt insult with probability 12.5%, and an ordinary update otherwise. The borderline replies
include sarcasm, terse reminders and criticism phrased as a question.

The producer calculates a base delay of one second per 200 characters of
current message text. It multiplies that delay by a uniform random factor between 0.8 and 1.2,
seeded by message ID so each message gets the same delay across runs. A 300-character message
therefore waits between 1.2 and 1.8 seconds, regardless of room history length.

Every message gets four independent primary judgments. The same judge step crosses two models
(GPT-6 Luna and GPT-5.6 Luna) with two rubrics. The direct rubric rates the speaker's conduct in the final
message. The recipient rubric starts with what the addressee would hear and how the speaker
treats them. Both use the same room context, sampling settings, reply schema and ordered severity
labels (`none`, `curt`, `disparaging`, `severe`). The judge node in the viewer is keyed by message,
model and rubric.

Within each rubric, agreement on severity settles the result. Two different valid ratings trigger
an independent GPT-6 Luna reading of the same message under that rubric. The tiebreaker sees only
the message and its context. Using the ordered median of three ratings returns the majority when
two match or the middle severity when all three differ. A missing required severity leaves that
message/rubric pair unresolved. The summary links to the final severity for each message and rubric.

For N messages and D disputed message/rubric pairs, the job requests 4N + D live judgments before
retries. D ranges from zero to 2N.
