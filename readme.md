# articy3RenPy Code Generator

The **articy3RenPy Code Generator** is a script that converts the JSON export of a given articy-project to RenPy code.  
It is designed for those who want to write the story of their RenPy game in articy:draft3 and generate complete RenPy code for it. 

The goals of this Code Generator are:
 - Preventing redundancies. Don't use articy to just plan out the flow of the game and then manually write RenPy code for it or you might run into consistency issues! If all the game logic is based on the articy-project, then the code will always be consistent with it. 
 - Enabling the use of articy's awesome story structuring capabilities. Visualising the flow of the game helps immensely if you want to create non-linear stories. Also, you can play through the text-based version of your game in articy even before testing it in RenPy! 
 - Generating code that is easy to debug. The Code Generator does not create one big RenPy file with several thousands lines of code. Instead, it creates a hierarchy of directories that represents the story structure as given in the articy-project.

## Quickstart

1. Open ``config.ini``:
    1. Set "ArticyExportFile" to the path of the JSON export file of your articy-project
    2. Set "RenPyArticyDir" to the path of the dir that shall contain the generated code. The directory must be inside the ``game`` folder of the RenPy game (it can also be in some subfolder in the hierarchy beneath ``game``, e.g. ``game/generated_files/articy``). 
2. Execute ``converter.py``

| :exclamation:  If there already is a directory at "RenPyArticyDir", its contents might be deleted! To prevent unintended deletions the script first checks if the files have a specific prefix and if the subfolders have the expected names. The files and subfolders will only be deleted if both look like they were generated by previous iterations of the Code Generator. Otherwise an error will be thrown. |
|-----------------------------------------|