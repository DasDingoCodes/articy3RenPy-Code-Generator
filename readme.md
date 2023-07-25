# articy3RenPy Code Generator

The **articy3RenPy Code Generator** is a script that converts the JSON export of a given articy-project to RenPy code. 
It is designed for those who want to develop their RenPy game with the help of articy:draft 3.

The goals of this Code Generator are:
 - Enabling the use of Articy's awesome story structuring capabilities. Visualising the flow of the game helps immensely if you want to create non-linear stories. Also, you can play through the text-based version of your game in Articy even before testing it in RenPy! 
 - Preventing redundancies. Don't use Articy to just plan out the flow of the game and then manually write RenPy code for it or you might run into consistency issues! If all the game logic is based on the Articy-project, then the code will always be consistent with it. 
 - Generating code that is easy to debug. The Code Generator does not create one big RenPy file with several thousands lines of code. Instead, it creates a hierarchy of directories that represents the story structure as given by the Articy-project. Also, a log file will give warnings in indicate precisely in which node they occured.

The Code Generator requires Python 3.9 or higher. As for RenPy, I have tested the Code Generator with RenPy 8.0.0. 
The generated code is pretty basic, I imagine it works with previous versions as well. 

## Table of Contents

 - [Showcase](#showcase)
   - [Menu with narration, dialogue and RenPy code](#menu-with-narration-dialogue-and-renpy-code)
   - [Conditions and instructions](#conditions-and-instructions)
   - [Articy entities to RenPy characters](#articy-entities-to-renpy-characters)
   - [Variables](#variables)
   - [Log file](#log-file)
 - [Quickstart](#quickstart)
 - [Setup Articy-Project](#setup-articy-project)
   - [Creating template for raw RenPy code](#creating-template-for-raw-renpy-code)
   - [(recommended) Create a single uppermost Flow Fragment](#recommended-create-a-single-uppermost-flow-fragment)
   - [(optional) Making it possible to pass parameters to Character objects](#optional-making-it-possible-to-pass-parameters-to-character-objects)
## Showcase

Here are some examples to give a short overview of the Code Generator's functionality. Open the images to see more details.

### Menu with narration, dialogue and RenPy code

![Example menu](images/showcase_00.png)

Example menu with narration, dialogue and RenPy commands. The coloured highlights show where each part of the generated code comes from. The red box with the RenPy code is the custom **RenPyBox** template as defined in the [setup](#Creating-template-for-raw-RenPy-code). Simple markdown parsing is enabled in this example ("\*Walk away\*" to "{i}Walk away{/i}").

### Conditions and instructions

![Example conditions and instructions](images/showcase_04.png)

Example with conditions and instructions. They can be set up with the ``Condition`` and ``Instruction`` nodes, or with the input and output pins of the nodes.

### Articy entities to RenPy characters

![Example characters](images/showcase_01.png)

Example of Character objects being created from Articy entities. *Bob Baker* has the unchanged default ``Supporting characters`` template. *Alice Smith* and *Player Character* have the default ``Main Characters`` template extended with the custom **RenPyCharacterParams** feature as defined in the [setup](#-(optional)-Making-it-possible-to-pass-parameters-to-Character-objects).

### Variables

![Example variables](images/showcase_02.png)

Example of Articy variables being set with their default values.

### Log file
```
game\chapter_1\articy_chapter_1.rpy
    label_0x01000000000007D0 references non-existent file "woof.mp3"
    label_0x01000000000007D0 contains the following line: # TODO: show the dog
game\chapter_2\articy_chapter_2.rpy
    label_0x01000000000007AA was not assigned any jump target in Articy, will jump to "end"
```

Example log file with three different types of log messages. 
The messages are grouped by the file they occured in.

## Quickstart

1. Edit ``config.ini``:
    1. Set "path_articy_json" to the path of the JSON export file of your Articy-project
    2. Set "path_target_dir" to the path of the dir that shall automatically be created and filled with the generated code. The directory must be inside the ``game`` folder of the RenPy game (it can also be in some subfolder in the hierarchy beneath ``game``, e.g. ``game/generated_files/articy``). 
2. Export your Articy-project as a JSON file to "path_articy_json"
3. Execute ``python converter.py``. This will take the ``config.ini`` file in the same folder as the configuration for the generator. You can also give a path to another .ini-file as a command line argument: ``python converter.py path/to/different.ini``

| :exclamation:  If there already is a directory at "path_target_dir", its contents might be deleted! To prevent unintended deletions the script first checks if the files have the prefix specified in the .ini-file and if the subfolders have the expected names (names of the uppermost flow fragments in the Articy-project). The files and subfolders will only be deleted if both look like they were generated by previous iterations of the Code Generator. Otherwise an error will be thrown. |
|-----------------------------------------|

During the development of your game your Articy-project keeps changing. To update your RenPy code, just repeat the steps above. The Code Generator will automatically remove the old files in "path_target_dir" and fill it with new code generated from "path_articy_json". 

## Setup Articy-project

### Creating template for raw RenPy code

[RenPy's say-statement](https://www.renpy.org/doc/html/dialogue.html#say-statement) is the most common statement in RenPy syntax. That is why the Code Generator assumes by default that the text in Articy's Dialogue Fragments are say-statements. 

For all other RenPy statements, we need to tell the Code Generator that an Articy object contains raw RenPy code. That is done by defining a custom template in the Articy-project:

1. Go to Template Design>Templates>Dialogue Fragments
2. Create a new Template called **RenPyBox** (other names can be specified by changing the ``renpy_box`` parameter in the .ini-file)
3. Open the template. In the Template parameters tab you should see the ``Display name`` and the ``Technical name``. The value of the ``Technical name`` must be **RenPyBox** (or another name given in the .ini-file). If it is not, edit the template. 
4. (optional) Give the template a striking colour. That way you see at first glance which parts of your Articy-project contain raw RenPy code. 

![RenPyBox Template](images/RenPyBox_template.png)

Now you should be able to add nodes of the type **RenPyBox** to the flow. Go to Flow and click on the drop down menu to the right of the ``Dialogue Fragment`` button. You should see the templates based on ``Dialogue Fragment``, i.e. **RenPyBox**. You can drag and drop it into the flow structure. 

![RenPyBox Selection](images/RenPyBox_selection.png)

### (recommended) Create a single uppermost Flow Fragment

The Code Generator needs to select some node in the Articy flow as the starting point for the generated code. It selects the first node it finds in the uppermost level of the flow hierarchy as the first element. To ensure that a predictable behaviour, I recommend a single Flow Fragment as the only element being the uppermost node. The name of the Flow Fragment can be chosen freely.

![Uppermost flow element](images/flow_uppermost_element.png)

### (optional) Making it possible to pass parameters to Character objects

This Code Generator creates [RenPy Character](https://www.renpy.org/doc/html/dialogue.html#Character) objects for all entities in the Articy-project. By default the name of the Articy entity is given as the ``name`` parameter of the Character class. However, you may want to create Characters with other parameters. For that you need to create custom feature in your Articy-project with the parameters you want to pass and you need to assign that feature to the entities.

Create the custom feature:

1. Go to Template Design>Features
2. Create a new feature called **RenPyCharacterParams** (other names can be specified by changing the ``features_renpy_character_params`` parameter in the .ini-file)
3. Open the feature and then press Edit.
4. In the Feature parameters tab you should see the ``Display name`` and the ``Technical name``. The value of the ``Technical name`` must be **RenPyCharacterParams** (or another name given in the .ini-file). If it is not, edit the ``Technical name``.
5. Add a ``Text (small)`` property to the feature by dragging it into the empty field in the middle. It should have the title ``Text (small)`` and an empty text field below.
6. Click on the property. In the Property parameters tab you should see the ``Display name`` and  ``Technical name`` of the property. Name both of them like the parameter you want to pass to the RenPy Character class, for example ``name`` or ``who_color``.
7. Repeat steps 5 and 6 for as many parameters you want. 
8. Press Apply and confirm the changes.

![RenPyCharacterParams](images/RenPyCharacterParams.png)

Assign the feature to the entities that shall pass the parameters to RenPy's Character class:

1. Go to Template Design>Templates>Entities. 
2. Open an entity that shall pass parameters to RenPys Character class (e.g. ``Main characters``) and press Edit.
3. In the Features tab you should see the newly created feature (e.g. **RenPyCharacterParams**). Drag and drop it into the field in the middle. 
4. Press Apply and confirm the changes. 

![Adding RenPyCharacterParams to Entity template](images/EntityEditor.png)

An entity of the type edited with the steps above (e.g. ``Main characters``) should now have the new feature. Open such an entity and go the Template tab, under **RenPyCharacterParams** you should see the properties you added to the feature. You can enter the parameters you want to pass by writing them into the text fields.

![Entity with RenPyCharacterParams](images/Entity_with_RenPyCharacterParams.png)