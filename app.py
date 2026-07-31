The only things I would still change
1. Increase contrast of the Welcome card
Currently:
Plain Text1Welcome to TrussLab2A guided practical from setup to submissionShow more lines
is excellent content-wise.
However the card still visually blends into the background.
I'd use:
CSS1background: white;2box-shadow: 0 4px 12px rgba(0,0,0,0.04);Show more lines
or
CSS1background: #fafcff;Show more lines
Very subtle.
Nothing dramatic.

2. Align heights of Welcome card columns
The right side checklist sits slightly high compared with the left text block.
Adding vertical centering would make it look more polished.
Visually:
Plain Text1[ Description           ] [ Checklist ]2[ Description           ] [ Checklist ]Show more lines
should sit on the same horizontal axis.

3. Make the Progress bar thicker
Current progress bar looks a little thin.
Maybe:

6 px → 10 px
slightly rounded ends

This would make progress feel more important.

4. Make the Apparatus card width slightly smaller
This is very minor.
The form is the primary task.
The apparatus is reference material.
I'd let:
Plain Text1Form:      68–70%2 3Diagram:   30–32%Show more lines
Currently it looks closer to 60/40.
Giving the form more width would improve usability.

5. Make "Not Selected" more noticeable
The pathway status:
Plain Text1Current pathway2Not selectedShow more lines
doesn't stand out.
Consider:
Plain Text1⚠ Pathway not selected2`Show more lines
or
Plain Text1Choose a practical pathway to continueShow more lines
in a light amber box.
Students will notice it immediately.

One thing I would remove
Top-right:
Plain Text1Designed by2Dr Mehdi KhatamifarShow more lines
For internal use it's fine, but from a UX perspective I would move that into:
Plain Text1About2Version3CreditsShow more lines
or the footer.
Commercial applications rarely place the author's name in prime page real estate.
The practical title is important.
The author is secondary.
