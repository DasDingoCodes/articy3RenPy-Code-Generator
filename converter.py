import json
from pathlib import Path
from utils import *
from configparser import ConfigParser
import shutil


path_config = Path(__file__).parent / 'config.ini'
config = ConfigParser()
config.read(path_config)

INDENT = '    '

############################
### Paths and file names ###
############################

# This file is the JSON export of the Articy project
PATH_ARTICY_EXPORT_FILE = config['Paths']['ArticyExportFile']
# The generated code will go in this directory
PATH_RENPY_ARTICY_DIR = config['Paths']['RenPyArticyDir']
# This is the prefix for all files under RenPyArticyDir
FILE_PREFIX = config['Paths']['GeneratedFilePrefix']
# Log file
LOG_FILE_NAME = config['Paths']['LogFileName']
# Generated code base file
BASE_FILE_NAME = config['Paths']['BaseFileName']
# Variables file 
VARIABLES_FILE_NAME = config['Paths']['VariablesFileName']
# Characters file
CHARACTERS_FILE_NAME = config['Paths']['CharactersFileName']


###########################
### RenPy code settings ###
###########################

# Prefix for the labels that can be jumped to
LABEL_PREFIX = config['Renpy']['LabelPrefix']
# Label of the RenPy block that ends the game
# All Articy generated blocks that don't have a target to jump to will jump to this block, immediately ending the game
END_LABEL = LABEL_PREFIX + config['Renpy']['EndLabel']
# Prefix for the character entities in RenPy
CHARACTER_PREFIX = config['Renpy']['CharacterPrefix']


####################
### Articy stuff ###
####################

# Technical names of the entity templates that contain characters
CHARACTER_ENTITY_TYPES = config['Articy']['CharacterEntityTypes'].split(",")
CHARACTER_ENTITY_TYPES = [x.strip() for x in CHARACTER_ENTITY_TYPES]
# Maps features to their properties that contain names of variable sets.
# For example: { feature_x : property_x }
# means that feature_x contains property_x and the value of property_x is the name of a variable set 
FEATURE_VARIABLE_SET_MAP = {
    'FeatureVariableSet' : 'VariablesSetName'
}
# name of the variable in a variable set that stores the name that 
# shall be displayed by RenPy when the associated charater speaks
VARIABLE_SET_CHARACTER_NAME = config['Articy']['VariableSetCharacterName']


class Converter:
    """
    A class converting Articy's JSON export file to RenPy code.
    """

    def __init__(self, path_json: Path, path_target_dir: Path):
        """
        Parameters
        ----------
        path_json : pathlib.Path
            Path towards Articy's JSON export file
        path_target_dir : pathlib.Path
            Path towards dir that shall contain the generated code. 
            Must be inside the "game" dir of the RenPy game.
        """

        self.path_json = path_json
        self.path_base_dir = path_target_dir

        self.path_renpy_game_dir = None
        for path_parent_dir in self.path_base_dir.absolute().parents:
            if path_parent_dir.name == "game":
                self.path_renpy_game_dir =  path_parent_dir
                break

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

        # set of all definitions in RenPy files. An error should be raised if something is defined twice
        self.renpy_definitions = set()

        # data that shall be logged
        # contains key:value pairs with keys being .rpy files and the values being lists of warnings for that file
        self.log_data = {}
    
    def run(self):
        self.read_data()
        self.clean_up()
        self.create_flow_hierarchy_dirs(self.hierarchy_flow[0], self.path_base_dir)
        self.write_base_file()
        self.write_characters_file()
        self.write_file_for_variables()
        for fragment_id in self.hierarchy_path_map:
            self.write_file_for_flow_fragment_id(fragment_id)
        self.write_log_file()
    
    def read_data(self):
        '''Read data from given json file and sets up model objects, in- and output-pins, hierarchy flow and global variables'''

        self.data = {}
        with open(self.path_json) as f:
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

        self.entity_id_to_character_name_map = {}
        self.renpy_definitions = set()
        self.log_data = {}

    def create_flow_hierarchy_dirs(self, hierarchy_element: dict, path_parent: Path):
        '''Creates directories for FlowFragments and updates the hierarchy_path_map'''
        element_id = hierarchy_element['Id']
        element_model = get_model_with_id(element_id, self.models)
        if element_model['Type'] != 'FlowFragment' and element_model['Type'] != 'Dialogue':
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
        if model_type == 'DialogueFragment':
            lines = self.lines_of_dialogue_fragment(model, rel_path_to_file)
        elif model_type == 'Dialogue': 
            if self.hierarchy_path_map[model_id] != path_file.parent:
                return
            lines = self.lines_of_dialogue(model, rel_path_to_file)
        elif model_type == 'FlowFragment':
            if self.hierarchy_path_map[model_id] != path_file.parent:
                return
            lines = self.lines_of_flow_fragment(model, rel_path_to_file)
        elif model_type == 'Jump':
            lines = self.lines_of_jump_node(model)
        elif model_type == 'Hub':
            lines = self.lines_of_hub_node(model, rel_path_to_file)
        elif model_type == 'RenPyBox':
            lines = self.lines_of_renpy_box(model, rel_path_to_file)
        elif model_type == 'Condition':
            lines = self.lines_of_condition_node(model)
        elif model_type == 'Instruction':
            lines = self.lines_of_instruction_node(model, rel_path_to_file)
        elif model_type == 'RenPyEntryPoint':
            lines = self.lines_of_renpy_entry_point(model, rel_path_to_file)
        elif model_type == 'RenPyBoxMenuChoice':
            lines = self.lines_of_renpy_box_menu_choice(model, rel_path_to_file)
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
        lines = self.lines_of_label(model)
        lines.extend(self.comment_lines(model,attr_to_ignore=['Text']))
        speaker_name = get_speaker_name(model, self.entity_id_to_character_name_map)
        model_text_lines = lines_of_model_text(model)
        for line in model_text_lines:
            lines.append(f'{INDENT}{speaker_name}\"{line}\"\n')
        lines.extend(self.lines_of_jump_logic(model, path_file))
        lines.append('\n')
        return lines

    def lines_of_renpy_box_menu_choice(self, model: dict, path_file: Path) -> list:
        '''Lines of RenPyBoxMenuChoice. May contain both RenPy code and dialogue/exposition'''
        text = model['Properties']['Text']
        stage_directions = model['Properties']['StageDirections']
        lines = self.lines_of_label(model)
        lines.extend(f'{INDENT}# RenPyBoxMenuChoice\n')
        if text:
            lines.extend(self.lines_of_renpy_logic(text, model, path_file))
        
        # if MenuText should be repeated after this Fragment was chosen then add it to the lines
        if 'dont_repeat_menu_text' not in stage_directions:
            speaker_name = get_speaker_name(model, self.entity_id_to_character_name_map)
            model_text_lines = lines_of_model_text(model, text_attr="MenuText")
            for line in model_text_lines:
                lines.append(f'{INDENT}{speaker_name}\"{line}\"\n')
            
        lines.extend(self.lines_of_jump_logic(model, path_file))
        lines.append('\n')
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
        model_target = model['Properties']['Target']
        lines = self.lines_of_label(model)
        lines.extend(self.comment_lines(model))
        lines.append(f'{INDENT}jump {LABEL_PREFIX}{model_target}\n')
        lines.append('\n')
        return lines

    def lines_of_hub_node(self, model: dict, path_file: Path) -> list:
        lines = self.lines_of_label(model)
        lines.extend(self.comment_lines(model))
        lines.extend(self.lines_of_jump_logic(model, path_file))
        lines.append('\n')
        return lines

    def lines_of_renpy_box(self, model: dict, path_file: Path) -> list:
        lines = self.lines_of_label(model)
        lines.extend(self.comment_lines(model,attr_to_ignore=['Text']))
        model_text = model['Properties']['Text']
        lines.extend(self.lines_of_renpy_logic(model_text, model, path_file))
        lines.extend(self.lines_of_jump_logic(model, path_file))
        lines.append('\n')
        return lines

    def lines_of_condition_node(self, model: dict) -> list:
        lines = self.lines_of_label(model)
        lines.extend(self.comment_lines(model, attr_to_ignore=['DisplayName']))
        condition_text = model['Properties']['Expression'].replace('\r', ' ').replace('\n', ' ')
        condition = convert_condition_from_articy_to_python(condition_text)
        lines.append(f'{INDENT}if {condition}:\n')
        target_id = model['Properties']['OutputPins'][0]['Connections'][0]['Target']
        target_label = f'{LABEL_PREFIX}{target_id}'
        lines.append(f'{INDENT*2}jump {target_label}\n')
        lines.append(f'{INDENT}else:\n')
        target_id = model['Properties']['OutputPins'][1]['Connections'][0]['Target']
        target_label = f'{LABEL_PREFIX}{target_id}'
        lines.append(f'{INDENT*2}jump {target_label}\n')
        lines.append('\n')
        return lines

    def lines_of_instruction_node(self, model: dict, path_file: Path) -> list:
        lines = self.lines_of_label(model)
        lines.extend(self.comment_lines(model, attr_to_ignore=['DisplayName']))
        lines.extend(self.lines_of_expression(model['Properties']['Expression']))
        lines.extend(self.lines_of_jump_logic(model, path_file))
        lines.append('\n')
        return lines

    def lines_of_renpy_entry_point(self, model: dict, path_file: Path) -> list:
        label = model['Properties']['Text']
        lines = [
            f'label {label}:\n',
            f'{INDENT}# RenPyEntryPoint\n'
        ]
        lines.extend(self.lines_of_jump_logic(model, path_file))
        lines.append('\n')
        return lines

    def lines_of_label(self, model: dict) -> list:
        '''Returns lines of the RenPy label logic'''
        model_id = model['Properties']['Id']
        self.add_new_definition(f'{LABEL_PREFIX}{model_id}')
        return [
            f'label {LABEL_PREFIX}{model_id}:\n'
        ]

    def lines_of_jump_logic(self, model: dict, path_file: Path) -> list:
        '''Returns the RenPy code lines for the jump logic for models of type FlowFragment, DialogueFragment, Hub, Instruction or RenPyBox.'''
        output_pins = get_output_pins_of_model(model)
        pins = output_pins
        # FlowFragments should use the input_pins for the next jump target because content in the FlowFragment is the next place that should be jumped to
        # But first check if there is content in the FlowFragment. 
        # If there is no Connection from the input pin of a FlowFragment to anything, then the FlowFragment does not have any element inside
        # In that case, use the output pin of the FlowFragment to jump to the next target
        if model['Type'] == 'FlowFragment' or model['Type'] == 'Dialogue':
            input_pins = get_input_pins_of_model(model)
            if 'Connections' in input_pins[0].keys():
                pins = input_pins

        model_id = model['Properties']['Id']
        if len(pins) == 0:
            self.log(path_file, f"No pins for model with ID {model_id}")
            return []
        elif 'Connections' not in pins[0] or len(pins[0]['Connections']) == 0:
            self.log(path_file, f"label_{model_id} was not assigned any jump target in Articy, will jump to {END_LABEL}")
            return [f'{INDENT}jump {END_LABEL}\n']
        elif len(pins[0]['Connections']) == 1:
            return self.lines_of_single_jump(pins[0], model_id, path_file)
        else:
            return self.lines_of_menu(pins)

    def lines_of_single_jump(self, output_pin: dict, model_id: str, path_file: Path) -> list:
        '''Lines of jump logic for a model with only one target to jump to.'''
        lines = []
        
        # Add instructions if output_pin contains any instructions in the text field
        lines.extend(self.lines_of_expression(output_pin['Text']))
        target_model_id = get_target_of_pin_recursively(output_pin, self.models, END_LABEL, self.input_pins, self.output_pins)
        if target_model_id == END_LABEL:
            self.log(path_file, f"label_{model_id} was not assigned any jump target in Articy, will jump to {END_LABEL}")
            target_label = target_model_id
        else:
            target_label = f'{LABEL_PREFIX}{target_model_id}'
        lines.append(f'{INDENT}jump {target_label}\n')
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
            path_to_img = path_to_img.replace('/' + FILE_PREFIX, '/')
            path_tmp = self.path_renpy_game_dir / path_to_img
            if not path_tmp.is_file():
                model_id = model['Properties']['Id']
                self.log(path_file, f"label_{model_id} references non-existent file {path_to_img}")
            # Lastly, replace the placeholder with the actual path
            line = line.replace('{'+img_name+'}', f'\'{path_to_img}\'')

        return line

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

    def lines_of_menu(self, pins: list) -> list:
        lines = [
            f'{INDENT}menu:\n'
        ]
        lines.append(f'{INDENT*2}extend ""\n\n') # extra line so that text box is still displayed in menu
        connections = pins[0]['Connections']
        # sort connections by the indices of their target models
        connections = sorted(connections, key=lambda connection: get_connection_index(connection, self.models))

        for connection in connections:
            choice_id = connection['Target']
            choice_label = f'{LABEL_PREFIX}{choice_id}'
            choice_input_pin_id = connection['TargetPin']
            choice_model = get_model_with_id(choice_id, self.models)
            choice_text = get_choice_text(choice_model)
            choice_text = preprocess_text(choice_text)
            # Check if there are conditions on the input pin of the choice
            choice_input_pin = get_input_pin_with_id(choice_input_pin_id, self.models, model=choice_model)
            # Make the condition a single line so that it can all fit in the same if statement
            choice_condition_text = choice_input_pin['Text'].replace('\r', ' ').replace('\n', ' ')
            choice_condition = convert_condition_from_articy_to_python(choice_condition_text)
            if choice_condition:
                lines.append(f'{INDENT*2}\"{choice_text}\" if {choice_condition}:\n')
            else:
                lines.append(f'{INDENT*2}\"{choice_text}\":\n')
            lines.append(f'{INDENT*3}jump {choice_label}\n')
        return lines

    def comment_lines(self, model: dict, attr_to_ignore: list = []) -> list:
        model_type = model['Type']
        lines = [
            f'{INDENT}# {model_type}\n'
        ]
        if 'DisplayName' not in attr_to_ignore and 'DisplayName' in model['Properties'].keys() and model['Properties']['DisplayName'] != '':
            model_display_name = model['Properties']['DisplayName']
            lines.append(f'{INDENT}# {model_display_name}\n')
        if 'StageDirections' not in attr_to_ignore and 'StageDirections' in model['Properties'].keys():
            model_stage_directions = model['Properties']['StageDirections']
            lines.extend(self.comment_lines_formatter(model_stage_directions))
        if 'Text' not in attr_to_ignore and 'Text' in model['Properties'].keys():
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
        path_file = self.hierarchy_path_map[flow_fragment_id] / f'{FILE_PREFIX}{self.hierarchy_path_map[flow_fragment_id].stem}.rpy'
        with open(path_file, 'w') as f:
            f.write('\n')
        flow_fragment = get_model_with_id(flow_fragment_id, self.models)
        self.write_lines_for_model(flow_fragment, path_file)
        child_models = get_models_with_parent(flow_fragment_id, self.models)
        for child in child_models:
            self.write_lines_for_model(child, path_file)

    def write_file_for_variables(self):
        '''Writes a file for all variables'''
        path_file = self.path_base_dir / VARIABLES_FILE_NAME
        lines = []
        for namespace in self.global_variables:
            lines.extend(self.lines_of_namespace(namespace))
        with open(path_file, 'w') as f:
            f.writelines(lines)

    def lines_of_namespace(self, namespace: dict) -> list:
        '''Returns the RenPy lines for a namespace i.e. set of variables'''
        name = namespace['Namespace']
        name = name[0].lower() + name[1:]
        description = namespace['Description']
        self.add_new_definition(name)
        lines = [
            f'init python in {name}:\n'
        ]
        lines.extend(self.comment_lines_formatter(description))
        lines.append('\n')
        for variable in namespace['Variables']:
            lines.extend(self.lines_of_variable(variable))
        lines.append('\n')
        return lines

    def lines_of_variable(self, variable: dict, indent_lvl=1) -> list:
        '''Returns the RenPy lines for setting up a variable.
        indent_lvl default is 1 because it is assumed that the variable is set up in 
        a namespace (Articy) / named store (RenPy).'''
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
            lines.extend(self.comment_lines_formatter(description, indent_lvl=indent_lvl))
        lines.append(f'{INDENT*indent_lvl}{name} = {value}\n\n')
        return lines

    def write_base_file(self):
        '''Writes a file with the start and end jump labels'''
        # The first model in the uppermost hierarchical element is assumed to be the starting point of the game
        start_id = self.hierarchy_flow[0]['Id']
        lines = [
            '# Entry point of the game\n',
            'label start:\n',
            f'{INDENT}jump {LABEL_PREFIX}{start_id}\n',
            '\n',
            f'label {LABEL_PREFIX}{END_LABEL}:\n',
            f'{INDENT}return\n'
        ]
        self.path_base_file = self.path_base_dir / BASE_FILE_NAME
        with open(self.path_base_file, 'w') as f:
            f.writelines(lines)

    def write_characters_file(self):
        '''Writes a file with the definitions of characters'''
        path_file = self.path_base_dir / CHARACTERS_FILE_NAME
        lines = []
        for model in self.models:
            if "Template" not in model.keys():
                continue
            template_name = get_template_display_name_by_type(model["Type"], self.data["ObjectDefinitions"])
            if template_name not in CHARACTER_ENTITY_TYPES:
                continue

            lines.extend(self.lines_of_character_definition(model))
            lines.append('\n')
        with open(path_file, 'w') as f:
            f.writelines(lines)

    def lines_of_character_definition(self, model: dict) -> list:
        '''Returns RenPy code lines for the definition of the given character'''
        lines = []
        # First find out what name shall be displayed in the game
        name_variable = ''
        name_variable_dynamic = False
        # find out if variable set is associated with character
        for feature_name in model['Template']:
            # skip if feature does not contain a variable set property
            if feature_name not in FEATURE_VARIABLE_SET_MAP.keys():
                continue
            variable_set_name_property = FEATURE_VARIABLE_SET_MAP[feature_name]
            variable_set_name = model['Template'][feature_name][variable_set_name_property]
            # skip if no variable set is associated with the character 
            if variable_set_name == '':
                continue
            name_variable = f'{variable_set_name}.{VARIABLE_SET_CHARACTER_NAME}'
            name_variable_dynamic = True
        # if name is still empty, take the display name of the entity
        if name_variable == '':
            name_variable = model['Properties']['DisplayName']
        name_variable = add_escape_characters(name_variable)
        # find out what name RenPy shall use internally for the character
        character_name = CHARACTER_PREFIX + str(model['Properties']['DisplayName']).split(' ')[0].lower()
        character_name = get_free_character_name(character_name, self.entity_id_to_character_name_map)
        self.entity_id_to_character_name_map[model['Properties']['Id']] = character_name
        self.add_new_definition(character_name)
        lines.append(
            f'define {character_name} = Character("{name_variable}", dynamic={str(name_variable_dynamic)})\n'
        )
        return lines
    
    def log(self, path: Path, msg: str) -> None:
        if path in self.log_data.keys():
            self.log_data[path].append(msg)
        else:
            self.log_data[path] = [msg]
    
    def write_log_file(self) -> None:
        
        path_log_file = self.path_base_dir / LOG_FILE_NAME

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
        Currently that means removing path_base_dir and its content so that new content can be generated'''
        
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
                raise UnexpectedContentException(f"Did not expect directory \"{path_item.name}\" in directory {self.path_base_dir}")

            if not path_item.is_dir() and FILE_PREFIX != path_item.name[:len(FILE_PREFIX)]:
                raise UnexpectedContentException(f"Did not expect file \"{path_item.name}\" in directory {self.path_base_dir}")

        # remove path_base_dir and its contents
        shutil.rmtree(self.path_base_dir)


if __name__ == '__main__':
    converter = Converter(
        PATH_ARTICY_EXPORT_FILE,
        PATH_RENPY_ARTICY_DIR
    )
