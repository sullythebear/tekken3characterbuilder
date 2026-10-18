DIZZY CHARACTER CREATOR 0.6.0
=============================

Works with Tekken 3 Expanded (recommended) and with Tekken3Recompiled 0.1.4.

Install
-------
1. Put the "character-builder" folder in the main folder of your game
   (the folder with game.toml). Working in a copy is recommended.
2. Double-click "Start Dizzy Character Creator.cmd". It opens in its own
   window. Keep the black console window open while you use it.

With Tekken 3 Expanded
----------------------
- Step 1 adds a CUSTOM page to the select screen (once).
- Step 2 rebuilds the game (once, and again after game updates).
- Every fighter you save goes on the CUSTOM page with its own portrait and
  name plate. On the select screen, press R2 twice (or L2 once) to get there.
  Saving, deleting or importing a fighter updates the page right away; just
  restart the game. No rebuild needed.
- Up to 12 fighters fit on the CUSTOM page.
- Names use Tekken 3's own name font: there is no F or Q, and 2 is the only
  digit. Very long names do not fit the name plate.
- Custom fighters are CPU opponents too, as the TTT1 guests are: at stages
  5-8 in Arcade and Time Attack, in Survival, Team Battle and Tekken Ball.
- The creator never removes a fighter from the CUSTOM page on its own.
  Fighters the game has that are not in this creator's "characters"
  folder (for example from another copy of the creator) are listed under
  "On the Custom page, not in this library": add them to your library
  (their portrait is taken from the game files) or remove them from the
  game after confirming.

With Tekken3Recompiled
----------------------
- Your fighter uses Jun's slot while you play through the creator. Starting
  the game from the normal launcher gives you the normal game with Jun.

Sharing
-------
"Export" creates a .t3char file you can share. Others load it with
"Import package". A package only contains a description, images and, for a
fighter with its own 3D model, the model's source file (.fbx/.glb) with your
choices; the receiving creator builds the model again. Never game files or
programs.

Costumes and colours
--------------------
With Tekken 3 Expanded, "3D model" (above the portrait) shows your fighter's
costumes in 3D, read from your own disc the first time (kept in the "cache"
folder). Drag to turn, scroll to zoom, double-click to reset.
On the "Builder" tab, "+ Colour variant" makes a
recoloured copy of a costume. Under "Clothing" every piece of clothing and
accessory is listed (click one, or click it on the model): give it a colour,
or open it to change its colours one by one. "Whole costume" shifts all
colours at once, "Schemes" colours the biggest pieces in one go ("Surprise me":
a random matching scheme). Under "In the
game" choose where it goes: it can replace one of the style's costumes, or,
for styles with two costumes, be costume 3 (press Start on the select
screen). Save, Update/Build if the creator asks, then restart the game.

Body parts (Builder tab)
------------------------
With Tekken 3 Expanded, "Body parts" builds a body from Tekken 3's own
fighters: head, body, arms and legs, each from any fighter of a similar build
(read from your own disc; packages carry only your choices). "Randomize"
picks for you; "Build" puts it on the chosen costume. Undo is on the Model
Importer tab. A costume with an own model keeps that model's colours.
Body colours (hue, saturation, lightness, keep skin tones) and body shape
(head size; arms, legs and body thicker or thinner; presets Slim, Athletic,
Heavy, Big head) work on the same build. "Save this look" keeps the parts,
colours and shape under a name, to use on any fighter. When a mix's textures
do not fit Tekken 3's one texture page, some parts get their textures at half
size (the preview says so). Taller or shorter fighters are not possible: the
animations set the height.

Own 3D models (Model Importer tab)
---------------------------------
With Tekken 3 Expanded, the "Model Importer" tab gives a fighter its own model:
choose a rigged .fbx (FBX Binary) or .glb file in T-pose or A-pose. Models
without a skeleton are locked. Big models are reduced to PS1 size with a new
texture (1 to 3 minutes). Hair, tails or horns that stick out are folded
down; change that per part before you import. "What makes a model work
well?" on that tab lists the details.
Before you import, a check list shows the geometry, materials and rigging.
Big models have "Face detail" and "Body detail". If the model's texture is a
separate image file, use "Choose texture image" (.png or .jpg).

Portrait Lab
------------
Choose an image, or (with an own 3D model) "Make from 3D model" with an
angle, framing, light and background. "Keep this portrait" saves it under
"Saved portraits" (up to 12): click one to use it again.

Voice Lab
---------
The announcer calls your fighter's name in Practice, as Tekken 3 does for its
own fighters. Silent unless you choose: your own recording or sound file
(pitch, echo, or the Announcer preset), or Windows' computer voice (choose
which of the voices installed on your computer).

Stage Lab
---------
Your fighter's home stage and theme (where it is met in Arcade), and the
stage's colours: night, sunset, dusk, ice, inferno, black and white, or your
own colour. New stage shapes are not possible.

Move Lab
--------
The moves of your fighter's style, as Tekken 3's COMMAND LIST shows them
(read from your disc), and the damage of every basic input (1, 2, 3, 4 with
the directions). Change a number to give your fighter other damage: it applies
to your fighter only (game patch T3CB-PATCH-20), not to the style's own
fighter, and not in a mirror match, where both players share one moveset.

Library
-------
"Check library" (menu) checks every fighter against the game folder.
"Asset library" lists your own assets (3D model source, portrait image,
recording) with where they come from; fill in "Credits and licences" on the
Fighter tab. Export warns when an asset in the package has no known licence.
"Back up all fighters" saves every fighter in one .t3backup file; "Import
package" reads it back.

Restore points
--------------
Every save keeps the settings it replaced (the last 20). "Restore point" on
the Fighter tab brings one back; the replaced settings become a restore
point too.

Test
----
"Test" (next to Play) builds the game if needed, starts it, and when you
close the game writes logs/test-report.md: versions, build result, the
Custom page list and the game's Custom/TTT1 log lines. It also appears in
the creator under "Test report", with a Copy button.

Undo
----
Click the Project bar at the top left and choose "Remove the creator's
changes". Rebuild the game afterwards. Your fighters stay in the
"characters" folder.

This is an unofficial fan project. Tekken is a trademark of Bandai Namco.
