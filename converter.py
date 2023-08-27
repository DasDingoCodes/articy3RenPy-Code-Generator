import json
from pathlib import Path
from utils import *
from configparser import ConfigParser
import shutil
import os
import sys
import logging


INDENT = '    '

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %I:%M:%S')

class Converter:
    """
    A class converting Articy's JSON export file to RenPy code.
    """

    def __init__(
        self, 
        path_articy_json: str, 
        path_target_dir: str,
        file_prefix: str = "articy_",
        log_file_name: str = "log.txt",
        base_file_name: str = "start.rpy",
        variables_file_name: str = "variables.rpy",
        characters_file_name: str = "characters.rpy",
        label_prefix: str = "label_",
        start_label: str = "start",
        end_label: str = "end",
        character_prefix: str = "character.",
        features_renpy_character_params: str = "RenPyCharacterParams",
        renpy_character_name: str = "RenPyCharacterName",
        renpy_box: str = "RenPyBox",
        menu_display_text_box: str = "True",
        beginnings_log_lines: str = "# todo, #todo",
        markdown_text_styles: str = "False",
        relative_imgs_in_braces: str = "False",
        repeat_menu_text: str = "False",
        **kwargs
    ):
        """
        Parameters
        ----------
        path_articy_json : str
            Path towards Articy's JSON export file
        path_target_dir : str
            Path towards dir that shall contain the generated code. 
            Must be inside the "game" dir of the RenPy game.
        file_prefix : str (default: "articy_") 
            Prefix that will be added in front of each generated file.
        log_file_name : str (default: "log.txt")
            Name of the log file. The file_prefix will be prepended.
        base_file_name : str (default: "start.rpy")
            Name of the file that contains start label. The file_prefix will be prepended.
        variables_file_name : str (default: "variables.rpy")
            Name of the file that contains the generated named stores. The file_prefix will be prepended.
        label_prefix : str (default: "label_")
            Prefix that will be added to all auto-generated labels except start_label and end_label. Needs to start with a character.
        start_label : str (default: "start")
            Label of the RenPy block at the start of the articy generated content. 
            If "start", then it is also the start of the RenPy game.  
        end_label : str (default: "end")
            Label of the RenPy block that blocks will jump to if they don't have a jump target in Articy. 
            The block only returns, thus ending the game.
        character_prefix : str (default: "character.")
            Prefix that will be added to the generated character objects.
        features_renpy_character_params : str (default "RenPyCharacterParams")
            Manually created features that contain parameters for RenPy characters. 
            Can be multiple comma separated values.
            The property of such a feature should be a parameter name of the RenPy Character class. 
            For example, the feature "RenPyCharacterParams" contains the property "name" and its value is "'Alice'".
            Then the Character object will be generated with "Character([...]name='Alice',[...])". 
            If an entity does not contain a name value or property, then the name parameter will be automatically set to the entity's display name. 
        renpy_character_name : str (default "RenPyCharacterName")
            Technical name of property that contains the name RenPy shall use for a character
            Will only be used if it is set in a feature of features_renpy_character_params
        renpy_box : str (default: "RenPyBox") 
            Name of the template that indicates a block with RenPy-code. 
            RenPy-code as in non-narration or non-dialogue, that is.
        menu_display_text_box : str (default: "True")
            Whether to display the text box when displaying menu choices.
        beginnings_log_lines : str (default: "# todo, #todo")
            RenPy code lines beginning with the following comma separated strings will be logged.
            Before checking if a line start with such a beginning, all texts are converted to lower case. 
            So "# TODO: do the thing" would be logged with the default "# todo" 
        markdown_text_styles : str (default: "False")
            Whether to parse simple markdown text styles, i.e. *italics*, **bold** or _underlined_. 
            Can be overwritten for a model with the stage directions "markdown=True" or "markdown=False"
        relative_imgs_in_braces : str (default: "False")
            Whether to parse "{img_name.png}" to "images/path/to/flow_fragment/img_name.png"
            Can be overwritten for a model with the stage directions "relative_img=True" or "relative_img=False"
        repeat_menu_text : str (default: "False")
            Whether to repeat the Menu Text of a RenPyBox after the content of the Text field, useful for menus.
            Can be overwritten for a model with the stage directions "repeat_menu_text=True" or "repeat_menu_text=False"
        """

        self.path_articy_json = Path(path_articy_json)
        self.path_base_dir = Path(path_target_dir)
        self.file_prefix = file_prefix
        self.log_file_name = file_prefix + log_file_name
        self.base_file_name = file_prefix + base_file_name
        self.variables_file_name = file_prefix + variables_file_name
        self.characters_file_name = file_prefix + characters_file_name
        self.label_prefix = label_prefix
        self.start_label = start_label
        self.end_label = end_label
        self.character_prefix = character_prefix
        self.features_renpy_character_params = string_to_list(features_renpy_character_params)
        self.renpy_character_name = renpy_character_name
        self.renpy_box_types = string_to_list(renpy_box)
        self.menu_display_text_box = menu_display_text_box.lower() == "true"
        self.beginnings_log_lines = string_to_list(beginnings_log_lines)
        self.markdown_text_styles = markdown_text_styles.lower() == "true"
        self.relative_imgs_in_braces = relative_imgs_in_braces.lower() == "true"
        self.repeat_menu_text = repeat_menu_text.lower() == "true"

        self.path_renpy_game_dir = None
        for path_parent_dir in self.path_base_dir.absolute().parents:
            if path_parent_dir.name == "game":
                self.path_renpy_game_dir =  path_parent_dir
                break
        if self.path_renpy_game_dir is None:
            msg = f"Did not find a \"game\" folder in path \"{self.path_base_dir}\""
            raise UnexpectedContentException(msg)

        # object that shall contain all the JSON data
        self.data = {}

        # all Articy models (flow fragments, dialogue fragments, hubs, etc) 
        self.models = []

        # input and output pins of the models
        self.input_pins = set()
        self.output_pins = set()

        # hierarchy of Articy models
        self.hierarchy_flow = {}

        # paths towards each file with generated RenPy code
        self.hierarchy_path_map = {}

        # Articy variables
        self.global_variables = []

        # this will map entity ids to RenPy Character instance names 
        # map will be filled later on when characters are created
        self.entity_id_to_character_name_map = {}

        # set of all technical names for entity templates 
        self.entity_types = {}

        # dict storing type names inheriting from the base nodes
        self.node_type_inheritance = {
            'Condition': {'Condition'},
            'DialogueFragment': {'DialogueFragment'},
            'Dialogue': {'Dialogue'},
            'FlowFragment': {'FlowFragment'},
            'Hub': {'Hub'},
            'Instruction': {'Instruction'},
            'Jump': {'Jump'}
        }

        # set of all definitions in RenPy files. An error should be raised if something is defined twice
        self.renpy_definitions = set()

        # data that shall be logged
        # contains key:value pairs with keys being .rpy files and the values being lists of warnings for that file
        self.log_data = {}
    
    def run(self):
        logging.info("Reading data...")
        self.read_data()
        logging.info("Cleaning directory...")
        self.clean_up()
        logging.info("Creating flow hierarchy...")
        for uppermost_flow_fragment in self.hierarchy_flow:
            self.create_flow_hierarchy_dirs(uppermost_flow_fragment, self.path_base_dir)
        logging.info("Writing base file...")
        self.write_base_file()
        logging.info("Writing character file...")
        self.write_characters_file()
        logging.info("Writing variables file...")
        self.write_file_for_variables()
        logging.info("Writing flow fragment files...")
        for fragment_id in self.hierarchy_path_map:
            self.write_file_for_flow_fragment_id(fragment_id)
        logging.info("Writing log file...")
        self.write_log_file()
        logging.info("Done")
    
    def read_data(self):
        '''Read data from given json file and sets up model objects, in- and output-pins, hierarchy flow and global variables'''

        self.data = {}
        with open(self.path_articy_json) as f:
            self.data = json.load(f)
        
        self.models = self.data['Packages'][0]['Models']

        self.input_pins = set()
        for model in self.models:
            if not 'InputPins' in model['Properties']:
                continue
            for input_pin in model['Properties']['InputPins']:
                self.input_pins.add(input_pin['Id'])

        self.output_pins = set()
        for model in self.models:
            if not 'OutputPins' in model['Properties']:
                continue
            for output_pin in model['Properties']['OutputPins']:
                self.output_pins.add(output_pin['Id'])

        self.hierarchy_flow = {}
        for i in self.data['Hierarchy']['Children']:
            if i['Type'] == 'Flow':
                self.hierarchy_flow = i['Children']
        self.hierarchy_path_map = {}

        self.global_variables = self.data['GlobalVariables']

        self.entity_types = set()
        for obj in self.data['ObjectDefinitions']:
            # skip non-entities
            if obj['Class'] != 'Entity':
                continue
            self.entity_types.add(obj['Type'])

        self.node_type_inheritance = {
            'Condition': {'Condition'},
            'DialogueFragment': {'DialogueFragment'},
            'Dialogue': {'Dialogue'},
            'FlowFragment': {'FlowFragment'},
            'Hub': {'Hub'},
            'Instruction': {'Instruction'},
            'Jump': {'Jump'}
        }
        for obj in self.data['ObjectDefinitions']:
            if obj['Class'] not in self.node_type_inheritance.keys():
                continue
            if obj['Type'] in self.renpy_box_types:
                continue
            self.node_type_inheritance[obj['Class']].add(
                obj['Type']
            )

        self.entity_id_to_character_name_map = {}
        self.renpy_definitions = set()
        self.log_data = {}

    def create_flow_hierarchy_dirs(self, hierarchy_element: dict, path_parent: Path):
        '''Creates directories for FlowFragments and updates the hierarchy_path_map'''
        element_id = hierarchy_element['Id']
        element_model = get_model_with_id(element_id, self.models)
        if element_model['Type'] not in self.node_type_inheritance['FlowFragment']:
            if element_model['Type'] not in self.node_type_inheritance['Dialogue']:
                return
        element_display_name = element_model['Properties']['DisplayName']
        element_display_name = element_display_name.lower().replace(' ', '_')
        path_element_dir = (Path) (path_parent / element_display_name)
        path_element_dir.mkdir(exist_ok=True, parents=True)
        self.hierarchy_path_map[element_id] = path_element_dir
        if 'Children' not in hierarchy_element.keys():
            return
        for child in hierarchy_element['Children']:
            self.create_flow_hierarchy_dirs(child, path_element_dir)

    def write_lines_for_model(self, model: dict, path_file: Path):
        '''Appends the RenPy-code for the given model to the given file'''
        ignore_model_types = ['Comment']
        lines = []
        model_type = model['Type']
        model_id = model['Properties']['Id']
        rel_path_to_file = path_file.relative_to(self.path_base_dir)
        if model_type in self.node_type_inheritance['DialogueFragment']:
            lines = self.lines_of_dialogue_fragment(model, rel_path_to_file)
        elif model_type in self.node_type_inheritance['Dialogue']: 
            if self.hierarchy_path_map[model_id] != path_file.parent:
                return
            lines = self.lines_of_dialogue(model, rel_path_to_file)
        elif model_type in self.node_type_inheritance['FlowFragment']:
            if self.hierarchy_path_map[model_id] != path_file.parent:
                return
            lines = self.lines_of_flow_fragment(model, rel_path_to_file)
        elif model_type in self.node_type_inheritance['Jump']:
            lines = self.lines_of_jump_node(model)
        elif model_type in self.node_type_inheritance['Hub']:
            lines = self.lines_of_hub_node(model, rel_path_to_file)
        elif model_type in self.renpy_box_types:
            lines = self.lines_of_renpy_box(model, rel_path_to_file)
        elif model_type in self.node_type_inheritance['Condition']:
            lines = self.lines_of_condition_node(model, rel_path_to_file)
        elif model_type in self.node_type_inheritance['Instruction']:
            lines = self.lines_of_instruction_node(model, rel_path_to_file)
        elif model_type in ignore_model_types:
            # do nothing for these 
            pass
        else:
            self.log(rel_path_to_file, f"Type \"{model_type}\" of model {model_id} is not supported")
        if not lines:
            return
        with(open(path_file, 'a') as f):
            f.writelines(lines)

    def lines_of_dialogue_fragment(self, model: dict, path_file: Path) -> list:
        '''Returns lines of a dialogue fragment, either dialogue or narration.'''
        lines = self.lines_of_label(model)
        lines.extend(self.comment_lines(model,attr_to_ignore=['Text', 'StageDirections']))
        lines.extend(self.lines_of_renpy_say(model, INDENT))
        lines.extend(self.lines_of_jump_logic(model, path_file))
        lines.append('\n')
        invalid_stage_directions = get_invalid_stage_directions(
            model,
            choice_index=True,
            string_arguments = [
                "speaker",
                "before",
                "after",
                "label"
            ],
            bool_arguments = [
                "markdown",
                "display_text_box"
            ]
        )
        label = get_label(model, label_prefix=self.label_prefix)
        for invalid_stage_direction in invalid_stage_directions:
            self.log(path_file, f"{label} invalid stage direction: {invalid_stage_direction}")
        return lines
    
    def lines_of_renpy_say(self, model: dict, indentation: str, **kwargs) -> list[str]:
        '''Returns lines of the RenPy say statement for a given model with some indentation.

        A line is as follows: {speaker_name}{instructions_before}"{line}"{instructions_after}
            speaker_name: (optional)
                Specified by StageDirections (e.g. 'speaker="Alice"') or by the model being assigned to an entity.
                A space character will be appended if a speaker is set. 
            instructions_before: (optional)
                Specified by StageDirections (e.g. 'before="@ angry"').
                A space character will be appended if an instruction is set.
            line:
                The line will be preprocessed.
                That includes adding escape characters and parsing Markdown commands to RenPy text styles.
            instructions_after: (optional)
                Specified by StageDirections (e.g. 'after="with vpunch"')
                A space character will be prepended if an instruction is set.

        By default the raw model lines are taken from the Text attribute of the model.
        But additional keyword arguments can be specified to extract the lines from other attributes.
        For example, text_attr="MenuText" and separator="\r\n" extract from MenuText.
        The keyword arguments should correspond to the lines_of_model_text function. 
        '''
        # get speaker name, if there is one, then append " " after it
        speaker_name = get_speaker_name(model, self.entity_id_to_character_name_map)
        if speaker_name != "":
            speaker_name = speaker_name + " "
        stage_directions = model['Properties']['StageDirections']
        # get instructions before
        instructions_before = get_substr_between(stage_directions, 'before="', '"')
        if instructions_before is None:
            instructions_before = ""
        else:
            instructions_before = instructions_before + " "
        # get instructions after
        instructions_after = get_substr_between(stage_directions, 'after="', '"')
        if instructions_after is None:
            instructions_after = ""
        else:
            instructions_after = " " + instructions_after
        markdown_text_styles = self.markdown_text_styles
        if has_stage_direction(model, "markdown=True"):
            markdown_text_styles = True
        elif has_stage_direction(model, "markdown=False"):
            markdown_text_styles = False
        model_text_lines = lines_of_model_text(model, markdown_text_styles, **kwargs)
        lines = []
        for line in model_text_lines:
            lines.append(f'{indentation}{speaker_name}{instructions_before}\"{line}\"{instructions_after}\n')
        return lines

    def lines_of_renpy_box(self, model: dict, path_file: Path) -> list:
        '''Lines of RenPyBox. 
        Mainly used to generate RenPy code. Generates dialogue/narration afterwards if given.
        RenPyBox should contain 
         - RenPy code in "Text"
         - (optional) dialogue/narration in "MenuText"
         - (optional) instructions in "StageDirections"'''
        text = model['Properties']['Text']
        lines = self.lines_of_label(model)
        lines.extend(f'{INDENT}# {model["Type"]}\n')
        if text:
            lines.extend(self.lines_of_renpy_logic(text, model, path_file))
        
        # if MenuText should be repeated after this Fragment was chosen then add it to the lines
        if model['Properties']['MenuText'] != "":
            repeat_menu_text = self.repeat_menu_text
            if has_stage_direction(model, "repeat_menu_text=True"):
                repeat_menu_text = True
            elif has_stage_direction(model, "repeat_menu_text=False"):
                repeat_menu_text = False
            if repeat_menu_text:
                lines.extend(self.lines_of_renpy_say(model, INDENT, text_attr="MenuText", separator="\r\n"))
            
        lines.extend(self.lines_of_jump_logic(model, path_file))
        lines.append('\n')
        invalid_stage_directions = get_invalid_stage_directions(
            model,
            choice_index=True,
            string_arguments = [
                "speaker",
                "before",
                "after",
                "label"
            ],
            bool_arguments = [
                "markdown",
                "display_text_box",
                "relative_img",
                "repeat_menu_text"
            ]
        )
        label = get_label(model, label_prefix=self.label_prefix)
        for invalid_stage_direction in invalid_stage_directions:
            self.log(path_file, f"{label} invalid stage direction: {invalid_stage_direction}")
        return lines

    def lines_of_flow_fragment(self, model:dict, path_file: Path) -> list:
        lines = self.lines_of_label(model)
        lines.extend(self.comment_lines(model))
        lines.extend(self.lines_of_jump_logic(model, path_file))
        lines.append('\n')
        return lines

    def lines_of_dialogue(self, model:dict, path_file: Path) -> list:
        lines = self.lines_of_label(model)
        lines.extend(self.comment_lines(model))
        lines.extend(self.lines_of_jump_logic(model, path_file))
        lines.append('\n')
        return lines

    def lines_of_jump_node(self, model:dict) -> list:
        model_target_id = model['Properties']['Target']
        lines = self.lines_of_label(model)
        lines.extend(self.comment_lines(model))
        target_model = get_model_with_id(model_target_id, self.models)
        target_label = get_label(target_model, label_prefix=self.label_prefix)
        lines.append(f'{INDENT}jump {target_label}\n')
        lines.append('\n')
        return lines

    def lines_of_hub_node(self, model: dict, path_file: Path) -> list:
        lines = self.lines_of_label(model)
        lines.extend(self.comment_lines(model))
        lines.extend(self.lines_of_jump_logic(model, path_file))
        lines.append('\n')
        return lines

    def lines_of_condition_node(self, model: dict, path_file: Path) -> list:
        lines = self.lines_of_label(model)
        lines.extend(self.comment_lines(model, attr_to_ignore=['DisplayName']))
        condition_text = model['Properties']['Expression'].replace('\r', ' ').replace('\n', ' ')
        condition = convert_condition_from_articy_to_python(condition_text)
        # if
        lines.append(f'{INDENT}if {condition}:\n')
        output_pin_if = model['Properties']['OutputPins'][0]
        lines.extend(self.lines_of_jump_logic_with_pins(model, path_file, [output_pin_if], indent_level=2))
        # else
        lines.append(f'{INDENT}else:\n')
        output_pin_else = model['Properties']['OutputPins'][1]
        lines.extend(self.lines_of_jump_logic_with_pins(model, path_file, [output_pin_else], indent_level=2))
        lines.append('\n')
        return lines

    def lines_of_instruction_node(self, model: dict, path_file: Path) -> list:
        lines = self.lines_of_label(model)
        lines.extend(self.comment_lines(model, attr_to_ignore=['DisplayName']))
        lines.extend(self.lines_of_expression(model['Properties']['Expression']))
        lines.extend(self.lines_of_jump_logic(model, path_file))
        lines.append('\n')
        return lines

    def lines_of_label(self, model: dict) -> list:
        '''Returns lines of the RenPy label logic'''
        label = get_label(model, label_prefix=self.label_prefix)
        self.add_new_definition(label)
        return [
            f'label {label}:\n'
        ]

    def lines_of_jump_logic(self, model: dict, path_file: Path) -> list:
        '''Returns the RenPy code lines for the jump logic for models that are not Condition or Jump nodes'''
        output_pins = get_output_pins_of_model(model)
        pins = output_pins
        # FlowFragments should use the input_pins for the next jump target because content in the FlowFragment is the next place that should be jumped to
        # But first check if there is content in the FlowFragment. 
        # If there is no Connection from the input pin of a FlowFragment to anything, then the FlowFragment does not have any element inside
        # In that case, use the output pin of the FlowFragment to jump to the next target
        if model['Type'] in self.node_type_inheritance['FlowFragment'] or model['Type'] in self.node_type_inheritance['Dialogue']:
            input_pins = get_input_pins_of_model(model)
            for pin in input_pins:
                if 'Connections' in pin.keys():
                    pins = input_pins

        model_id = model['Properties']['Id']
        if len(pins) == 0:
            self.log(path_file, f"No pins for model with ID {model_id}")
            return []
        return self.lines_of_jump_logic_with_pins(model, path_file, pins)
    
    def lines_of_jump_logic_with_pins(self, model: dict, path_file: Path, pins: list[dict], indent_level=1) -> list[str]:

        connections_num = get_connections_num(pins)
        if connections_num == 0:
            label = get_label(model, label_prefix=self.label_prefix)
            self.log(path_file, f"{label} was not assigned any jump target in Articy, will jump to \"{self.end_label}\"")
            return [f'{INDENT*indent_level}jump {self.end_label}\n']

        if connections_num == 1:
            output_pin = None
            for pin in pins:
                if 'Connections' not in pin or len(pin['Connections']) == 0:
                    continue
                output_pin = pin
            model_id = model['Properties']['Id']
            return self.lines_of_single_jump(output_pin, model_id, path_file, indent_level=indent_level)
        else:
            display_text_box = self.menu_display_text_box
            if has_stage_direction(model, "display_text_box=False"):
                display_text_box = False
            elif has_stage_direction(model, "display_text_box=True"):
                display_text_box = True
            return self.lines_of_menu(pins, display_text_box=display_text_box, indent_level=indent_level)

    def lines_of_single_jump(self, output_pin: dict, model_id: str, path_file: Path, indent_level: int = 1) -> list:
        '''Lines of jump logic for a model with only one target to jump to.'''
        lines = []
        
        # Add instructions if output_pin contains any instructions in the text field
        lines.extend(self.lines_of_expression(output_pin['Text']))
        target_model_id = get_target_of_pin_recursively(output_pin, self.models, self.input_pins, self.output_pins)
        if target_model_id == None:
            model = get_model_with_id(model_id, self.models)
            label = get_label(model, label_prefix=self.label_prefix)
            self.log(path_file, f"{label} was not assigned any jump target in Articy, will jump to \"{self.end_label}\"")
            target_label = self.end_label
        else:
            model = get_model_with_id(target_model_id, self.models)
            target_label = get_label(model, label_prefix=self.label_prefix)
        lines.append(f'{INDENT*indent_level}jump {target_label}\n')
        return lines

    def lines_of_renpy_logic(self, text: str, model: dict, path_file: Path, indent_lvl=1) -> list:
        '''Returns lines of RenPy logic from the given text'''
        lines = []
        for i, line in enumerate(text.split('\r\n')):
            if line:
                line = self.line_of_renpy_logic(line, model, path_file=path_file)
                line = f'{INDENT*indent_lvl}{line}\n'
                lines.append(line)
        return lines

    def line_of_renpy_logic(self, line: str, model: dict, path_file: Path) -> str:
        '''Interprets given line of model and outputs RenPy logic
        Example:
        input: scene image {test_img.png} with dissolve
        output: scene image 'images/game/test/test_img.png' with dissolve
        '''
        label = get_label(model, label_prefix=self.label_prefix)
        relative_imgs_in_braces = self.relative_imgs_in_braces
        if has_stage_direction(model, "relative_img=False"):
            relative_imgs_in_braces = False
        elif has_stage_direction(model, "relative_img=True"):
            relative_imgs_in_braces = True
        if relative_imgs_in_braces:
            while contains_img_call(line):
                img_name = get_substr_between(line, '{', '}')
                parent_id = model['Properties']['Parent']
                path_to_articy_folder = Path(self.hierarchy_path_map[parent_id])
                path_to_img = path_to_articy_folder
                # Go up in hierarchy if img_name starts with ../
                img_name_truncated = img_name
                while(img_name_truncated.startswith('../')):
                    path_to_img = path_to_img.parent
                    img_name_truncated = img_name_truncated[3:]
                path_to_img = path_to_img / img_name_truncated
                # Following line removes 'RenPy/<Project name>/game/articy' from path
                path_to_img = 'images' / path_to_img.relative_to(self.path_base_dir)
                path_to_img = str(path_to_img)
                path_to_img = path_to_img.replace('\\', '/')
                # Following line removes the directory prefixes
                path_to_img = path_to_img.replace('/' + self.file_prefix, '/')
                # Lastly, replace the placeholder with the actual path
                line = line.replace('{'+img_name+'}', f'\'{path_to_img}\'')

        # Check if line starts with something that should be logged, e.g. "# TODO"
        if text_starts_with(line, self.beginnings_log_lines):
            self.log(path_file, f"{label} contains the following line: {line}")
        # Check if referenced files exist, log if not
        self.check_file_references(line, path_file, label)

        return line
    
    def check_file_references(self, line: str, path_file: Path, label: str) -> None:
        '''Checks if referenced files in line exist. 
        Only image and audio files in quotation marks are considered.
        Logs if a referenced file does not exist.'''

        # Images
        image_endings = [".png", ".jpg", ".jpeg", ".webp", ".gif"]
        image_refs = []
        image_refs.extend(file_references(line, image_endings, '"'))
        image_refs.extend(file_references(line, image_endings, "'"))
        for img_reference in image_refs:
            path_reference = self.path_renpy_game_dir / img_reference
            if path_reference.is_file():
                continue
            path_reference = self.path_renpy_game_dir / "images" / img_reference
            if path_reference.is_file():
                continue
            self.log(path_file, f"{label} references non-existent file \"{img_reference}\"")

        # Audio files
        # remove angle brackets from strings like "<from 5 to 10>music.mp3"
        line = re.sub(r"<(.*?)>", "", line)
        audio_endings = [".mp3", ".wav", ".ogg", ".opus", ".flac"]
        audio_refs = []
        audio_refs.extend(file_references(line, audio_endings, '"'))
        audio_refs.extend(file_references(line, audio_endings, "'"))
        for audio_reference in audio_refs:
            path_reference = self.path_renpy_game_dir / audio_reference
            if path_reference.is_file():
                continue
            path_reference = self.path_renpy_game_dir / "audio" / audio_reference
            if path_reference.is_file():
                continue
            self.log(path_file, f"{label} references non-existent file \"{audio_reference}\"")

    def lines_of_expression(self, expression: str, indent_lvl: int = 1) -> list:
        lines = []
        instructions = convert_condition_from_articy_to_python(expression)
        instructions = instructions.replace('\n', '')
        instructions = instructions.replace('\r', '')
        instructions = instructions.split(';')
        for instruction in instructions:
            if instruction:
                lines.append(f'{INDENT*indent_lvl}$ {instruction}\n')
        return lines

    def lines_of_menu(self, pins: list, display_text_box: bool, indent_level: int = 1) -> list[str]:
        lines = [
            f'{INDENT*indent_level}menu:\n'
        ]
        if display_text_box:
            lines.append(f'{INDENT*(indent_level+1)}extend ""\n\n') # extra line so that text box is still displayed in menu
        
        for pin in pins:
            connections = pin['Connections']
            # sort connections by the indices of their target models
            connections = sorted(connections, key=lambda connection: get_connection_index(connection, self.models))

            for connection in connections:
                choice_id = connection['Target']
                choice_model = get_model_with_id(choice_id, self.models)
                choice_label = get_label(choice_model, label_prefix=self.label_prefix)
                choice_input_pin_id = connection['TargetPin']
                choice_text = get_choice_text(choice_model, connection)
                if choice_text == '':
                    raise InvalidArticy(f'Could not get choice text for connection with target model {choice_id}')
                markdown_text_styles = self.markdown_text_styles
                if has_stage_direction(choice_model, "markdown=True"):
                    markdown_text_styles = True
                elif has_stage_direction(choice_model, "markdown=False"):
                    markdown_text_styles = False
                choice_text = preprocess_text(choice_text, markdown_text_styles)
                # Check if there are conditions on the input pin of the choice
                choice_input_pin = get_input_pin_with_id(choice_input_pin_id, self.models, model=choice_model)
                # Make the condition a single line so that it can all fit in the same if statement
                choice_condition_text = choice_input_pin['Text'].replace('\r', ' ').replace('\n', ' ')
                choice_condition = convert_condition_from_articy_to_python(choice_condition_text)
                if choice_condition:
                    lines.append(f'{INDENT*(indent_level+1)}\"{choice_text}\" if {choice_condition}:\n')
                else:
                    lines.append(f'{INDENT*(indent_level+1)}\"{choice_text}\":\n')
                lines.extend(self.lines_of_expression(pin['Text'], indent_lvl=indent_level+2))
                lines.append(f'{INDENT*(indent_level+2)}jump {choice_label}\n')
        return lines

    def comment_lines(self, model: dict, attr_to_ignore: list = []) -> list:
        model_type = model['Type']
        lines = [
            f'{INDENT}# {model_type}\n'
        ]
        if 'DisplayName' not in attr_to_ignore and 'DisplayName' in model['Properties'] and model['Properties']['DisplayName'] != '':
            model_display_name = model['Properties']['DisplayName']
            lines.append(f'{INDENT}# {model_display_name}\n')
        if 'StageDirections' not in attr_to_ignore and 'StageDirections' in model['Properties']:
            model_stage_directions = model['Properties']['StageDirections']
            lines.extend(self.comment_lines_formatter(model_stage_directions))
        if 'Text' not in attr_to_ignore and 'Text' in model['Properties']:
            model_text = model['Properties']['Text']
            lines.extend(self.comment_lines_formatter(model_text))
        return lines

    def comment_lines_formatter(self, text: str, prefix='', suffix='', indent_lvl: int =1) -> list:
        text = text.replace('\r', '')
        lines = text.split('\n')
        lines = [line for line in lines if line != '']
        lines = [f'{INDENT*indent_lvl}# {prefix}{line}{suffix}\n' for line in lines]
        return lines

    def write_file_for_flow_fragment_id(self, flow_fragment_id: str):
        '''Writes a file for a FlowFragment and all elements that have that FlowFragment as a parent.
        The file contains the RenPy code of all mentioned elements.'''
        path_file = self.hierarchy_path_map[flow_fragment_id] / f'{self.file_prefix}{self.hierarchy_path_map[flow_fragment_id].stem}.rpy'
        with open(path_file, 'w') as f:
            f.write('\n')
        flow_fragment = get_model_with_id(flow_fragment_id, self.models)
        self.write_lines_for_model(flow_fragment, path_file)
        child_models = get_models_with_parent(flow_fragment_id, self.models)
        for child in child_models:
            self.write_lines_for_model(child, path_file)

    def write_file_for_variables(self):
        '''Writes a file for all variables'''
        path_file = self.path_base_dir / self.variables_file_name
        lines = []
        for namespace in self.global_variables:
            lines.extend(self.lines_of_namespace(namespace))
        with open(path_file, 'w') as f:
            f.writelines(lines)

    def lines_of_namespace(self, namespace: dict) -> list:
        '''Returns the RenPy lines for a namespace i.e. set of variables'''
        namespace_name = namespace['Namespace']
        namespace_name = namespace_name[0].lower() + namespace_name[1:]
        
        description = namespace['Description']
        self.add_new_definition(namespace_name)
        lines = [
            f'# Namespace: {namespace_name}\n'
        ]
        lines.extend(self.comment_lines_formatter(description, indent_lvl=0))
        lines.append('\n')
        for variable in namespace['Variables']:
            lines.extend(self.lines_of_variable(variable, namespace_name))
        lines.append('\n')
        return lines

    def lines_of_variable(self, variable: dict, namespace: str = "") -> list:
        '''Returns the RenPy lines for setting up a variable.'''
        supported_variable_types = {'Boolean', 'Integer', 'String'}
        if variable['Type'] not in supported_variable_types:
            raise ValueError(f'Unexpected variable type: {variable["Type"]} in {variable}')
        name = variable['Variable']
        description = variable['Description']
        if variable['Type'] == 'Boolean':
            value = variable['Value'] == 'True'
        elif variable['Type'] == 'Integer':
            value = int(variable['Value'])
        else:
            value = '\"' + variable['Value'] + '\"'
        lines = []
        if description:
            lines.extend(self.comment_lines_formatter(description, indent_lvl=0))
        if namespace:
            namespace = namespace + "."
        lines.append(f'default {namespace}{name} = {value}\n\n')
        return lines

    def write_base_file(self):
        '''Writes a file with the start and end jump labels'''
        # The first model in the uppermost hierarchical element is assumed to be the starting point of the game
        first_model_id = self.hierarchy_flow[0]['Id']
        first_model = get_model_with_id(first_model_id, self.models)
        first_model_label = get_label(first_model, label_prefix=self.label_prefix)
        lines = [
            '# Entry point of the game\n',
            f'label {self.start_label}:\n',
            f'{INDENT}jump {first_model_label}\n',
            '\n',
            f'label {self.end_label}:\n',
            f'{INDENT}return\n'
        ]
        self.path_base_file = self.path_base_dir / self.base_file_name
        with open(self.path_base_file, 'w') as f:
            f.writelines(lines)

    def write_characters_file(self):
        '''Writes a file with the definitions of characters'''
        path_file = self.path_base_dir / self.characters_file_name
        lines = []
        for model in self.models:
            if model['Type'] not in self.entity_types:
                continue

            lines.extend(self.lines_of_character_definition(model))
            lines.append('\n')
        with open(path_file, 'w') as f:
            f.writelines(lines)
    
    def lines_of_character_definition(self, model: dict) -> list:
        '''Returns RenPy code lines for the definition of the given character'''
        lines = []
        # get the parameters from the character features
        params = {}
        character_name = ""
        if 'Template' in model.keys():
            for feature_name in model['Template']:
                if feature_name not in self.features_renpy_character_params:
                    continue
                for parameter in model['Template'][feature_name]:
                    # skip if field was left empty
                    if model['Template'][feature_name][parameter] == "":
                        continue
                    if parameter == self.renpy_character_name:
                        # if the parameter contains the name RenPy shall use for the Character
                        # then remember it as the character_name
                        character_name = model['Template'][feature_name][parameter]
                    else:
                        # else store the parameter/value-pair in the parameter dictionary
                        params[parameter] = model['Template'][feature_name][parameter]
        # if no name was manually given, use the DisplayName of the model 
        if "name" not in params:
            params["name"] = f"\"{model['Properties']['DisplayName']}\""
        # if character has not been explicitly set, infer it
        if character_name == "":
            character_name = str(model['Properties']['DisplayName']).split(' ')[0].lower().strip()
        if character_name == "":
            character_name = "unnamed"
            path_file = self.path_base_dir / self.characters_file_name
            self.log(path_file, f"Unnamed character with ID {model['Properties']['Id']}")
        character_name = self.character_prefix + character_name
        character_name = get_free_character_name(character_name, self.entity_id_to_character_name_map)
        self.entity_id_to_character_name_map[model['Properties']['Id']] = character_name
        self.add_new_definition(character_name)
        lines.extend([
            f"# Entity: {model['Properties']['DisplayName']}\n",
            f'define {character_name} = Character(\n'
        ])
        for parameter in params:
            lines.append(f"{INDENT}{parameter}={params[parameter]},\n")
        lines.append(")\n")
        return lines
    
    def log(self, path: Path, msg: str) -> None:
        if path in self.log_data.keys():
            self.log_data[path].append(msg)
        else:
            self.log_data[path] = [msg]
    
    def write_log_file(self) -> None:
        
        path_log_file = self.path_base_dir / self.log_file_name

        with open(path_log_file, 'w') as f:
            f.write("\n")
        
        for path_file in self.log_data.keys():
            lines = [f"{path_file}\n"]
            for information in self.log_data[path_file]:
                lines.append(f"{INDENT}{information}\n")
            with open(path_log_file, 'a') as f:
                f.writelines(lines)

    def add_new_definition(self, new_definition: str):
        if new_definition in self.renpy_definitions:
            raise ValueError(f'ValueError: definition {new_definition} already used')
        else:
            self.renpy_definitions.add(new_definition)

    def clean_up(self) -> None:
        '''Cleans up folder before code gets generated.
        That means removing the contents of path_base_dir so that new content can be generated.
        Does not start removal if unexpected content is encountered.'''
        
        # if directory does not exist there is nothing to remove
        if not self.path_base_dir.exists():
            return

        # names of dirs that were (probably) generated by this converter
        expected_dir_names = []
        for hierarchy_element in self.hierarchy_flow:
            model = get_model_with_id(hierarchy_element["Id"], self.models)
            dir_name = model["Properties"]["DisplayName"]
            dir_name = dir_name.lower().replace(' ', '_')
            expected_dir_names.append(dir_name)

        # raise exception if path_base_dir contains unexpected content
        for path_item in self.path_base_dir.iterdir():

            if path_item.is_dir() and path_item.name not in expected_dir_names:
                msg = f"Did not expect directory \"{path_item.name}\" in directory {self.path_base_dir}"
                raise UnexpectedContentException(msg)

            if not path_item.is_dir() and self.file_prefix != path_item.name[:len(self.file_prefix)]:
                msg = f"Did not expect file \"{path_item.name}\" in directory {self.path_base_dir}"
                raise UnexpectedContentException(msg)

        # remove path_base_dir contents
        for filename in os.listdir(self.path_base_dir):
            file_path = os.path.join(self.path_base_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                msg = f'Failed to delete {file_path}. Reason: {e}'
                self.log_data[self.path_base_dir] = [msg]
                print(msg)


if __name__ == '__main__':

    if len(sys.argv) > 1:
        path_config = Path(sys.argv[1])
    else:
        path_config = Path(__file__).parent / 'config.ini'

    config = ConfigParser()
    config.read(path_config)

    parameters = dict()
    for section in config.sections():
        for (parameter, value) in config.items(section):
            parameters[parameter] = value
    
    converter = Converter(**parameters)
    converter.run()
