import json
from pathlib import Path
from utils import *
from configparser import ConfigParser
import shutil
import os
import sys


INDENT = '    '


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
        end_label: str = "end",
        character_prefix: str = "character_",
        features_renpy_character_params: str = "RenPyCharacterParams",
        renpy_box: str = "RenPyBox",
        renpy_entrypoint: str = "RenPyEntryPoint",
        menu_display_text_box: str = "True",
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
            Prefix that will be added to all auto-generated labels. Needs to start with a character.
        end_label : str (default: "end")
            Label of the RenPy block that blocks will jump to if they don't have a jump target in Articy. 
            The block only returns, thus ending the game.
            The label_prefix will be prepended.
        character_prefix : str (default: "character_")
            Prefix that will be added to the generated character objects.
        features_renpy_character_params : str (default "RenPyCharacterParams")
            Manually created features that contain parameters for RenPy characters. 
            Can be multiple comma separated values.
            The property of such a feature should be a parameter name of the RenPy Character class. 
            For example, the feature "RenPyCharacterParams" contains the property "name" and its value is "'Alice'".
            Then the Character object will be generated with "Character([...]name='Alice',[...])". 
            If an entity does not contain a name value or property, then the name parameter will be automatically set to the entity's display name. 
        renpy_box : str (default: "RenPyBox") 
            Name of the template that indicates a block with RenPy-code. 
            RenPy-code as in non-narration or non-dialogue, that is.
        renpy_entrypoint : str (default: "RenPyEntryPoint")
            Name of the template that is used to generated blocks with manually set labels.
        menu_display_text_box : str (default: "True")
            Whether to display the text box when displaying menu choices.
        """

        self.path_articy_json = Path(path_articy_json)
        self.path_base_dir = Path(path_target_dir)
        self.file_prefix = file_prefix
        self.log_file_name = file_prefix + log_file_name
        self.base_file_name = file_prefix + base_file_name
        self.variables_file_name = file_prefix + variables_file_name
        self.characters_file_name = file_prefix + characters_file_name
        self.label_prefix = label_prefix
        self.end_label = label_prefix + end_label
        self.character_prefix = character_prefix
        self.features_renpy_character_params = [x.strip() for x in features_renpy_character_params.split(',') if x.strip()]
        self.renpy_box = renpy_box
        self.renpy_entrypoint = renpy_entrypoint
        self.menu_display_text_box = menu_display_text_box.lower() == "true"

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
        elif model_type == self.renpy_box:
            lines = self.lines_of_renpy_box(model, rel_path_to_file)
        elif model_type == 'Condition':
            lines = self.lines_of_condition_node(model)
        elif model_type == 'Instruction':
            lines = self.lines_of_instruction_node(model, rel_path_to_file)
        elif model_type == self.renpy_entrypoint:
            lines = self.lines_of_renpy_entry_point(model, rel_path_to_file)
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

    def lines_of_renpy_box(self, model: dict, path_file: Path) -> list:
        '''Lines of RenPyBox. 
        Mainly used to generate RenPy code. Generates dialogue/narration afterwards if given.
        RenPyBox should contain 
         - RenPy code in "Text"
         - (optional) dialogue/narration in "MenuText"
         - (optional) instructions in "StageDirections"'''
        text = model['Properties']['Text']
        stage_directions = model['Properties']['StageDirections']
        lines = self.lines_of_label(model)
        lines.extend(f'{INDENT}# {self.renpy_box}\n')
        if text:
            lines.extend(self.lines_of_renpy_logic(text, model, path_file))
        
        # if MenuText should be repeated after this Fragment was chosen then add it to the lines
        if model['Properties']['MenuText'] != "" and 'dont_repeat_menu_text' not in stage_directions:
            speaker_name = get_speaker_name(model, self.entity_id_to_character_name_map)
            model_text_lines = lines_of_model_text(model, text_attr="MenuText", separator="\r\n")
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
        lines.append(f'{INDENT}jump {self.label_prefix}{model_target}\n')
        lines.append('\n')
        return lines

    def lines_of_hub_node(self, model: dict, path_file: Path) -> list:
        lines = self.lines_of_label(model)
        lines.extend(self.comment_lines(model))
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
        target_label = f'{self.label_prefix}{target_id}'
        lines.append(f'{INDENT*2}jump {target_label}\n')
        lines.append(f'{INDENT}else:\n')
        target_id = model['Properties']['OutputPins'][1]['Connections'][0]['Target']
        target_label = f'{self.label_prefix}{target_id}'
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
        self.add_new_definition(f'{self.label_prefix}{model_id}')
        return [
            f'label {self.label_prefix}{model_id}:\n'
        ]

    def lines_of_jump_logic(self, model: dict, path_file: Path) -> list:
        '''Returns the RenPy code lines for the jump logic for models that are not Condition or Jump nodes'''
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
            self.log(path_file, f"label_{model_id} was not assigned any jump target in Articy, will jump to {self.end_label}")
            return [f'{INDENT}jump {self.end_label}\n']
        elif len(pins[0]['Connections']) == 1:
            return self.lines_of_single_jump(pins[0], model_id, path_file)
        else:
            display_text_box = self.menu_display_text_box
            stage_directions = model['Properties']['StageDirections']
            if "dont_display_text_box" in stage_directions:
                display_text_box = False
            elif "display_text_box" in stage_directions:
                display_text_box = True
            return self.lines_of_menu(pins, display_text_box=display_text_box)

    def lines_of_single_jump(self, output_pin: dict, model_id: str, path_file: Path) -> list:
        '''Lines of jump logic for a model with only one target to jump to.'''
        lines = []
        
        # Add instructions if output_pin contains any instructions in the text field
        lines.extend(self.lines_of_expression(output_pin['Text']))
        target_model_id = get_target_of_pin_recursively(output_pin, self.models, self.end_label, self.input_pins, self.output_pins)
        if target_model_id == self.end_label:
            self.log(path_file, f"label_{model_id} was not assigned any jump target in Articy, will jump to {self.end_label}")
            target_label = target_model_id
        else:
            target_label = f'{self.label_prefix}{target_model_id}'
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
            path_to_img = path_to_img.replace('/' + self.file_prefix, '/')
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

    def lines_of_menu(self, pins: list, display_text_box: bool) -> list:
        lines = [
            f'{INDENT}menu:\n'
        ]
        if display_text_box:
            lines.append(f'{INDENT*2}extend ""\n\n') # extra line so that text box is still displayed in menu
        connections = pins[0]['Connections']
        # sort connections by the indices of their target models
        connections = sorted(connections, key=lambda connection: get_connection_index(connection, self.models))

        for connection in connections:
            choice_id = connection['Target']
            choice_label = f'{self.label_prefix}{choice_id}'
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
            f'{INDENT}jump {self.label_prefix}{start_id}\n',
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
        # find out what name RenPy shall use internally for the character
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
        params = {}
        if 'Template' in model.keys():
            for feature_name in model['Template']:
                if feature_name not in self.features_renpy_character_params:
                    continue
                for parameter in model['Template'][feature_name]:
                    # if the field is not empty
                    if model['Template'][feature_name][parameter] != "":
                        params[parameter] = model['Template'][feature_name][parameter]
        # if no name was manually given, use the DisplayName of the model 
        if "name" not in params:
            params["name"] = f"\"{model['Properties']['DisplayName']}\""
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
