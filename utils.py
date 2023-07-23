import re


def get_model_with_id(model_id: str, models: list) -> dict:
    '''Returns the model with model_id in models'''
    for i in models:
        if i['Properties']['Id'] == model_id:
            return i
    return None

def get_input_pins_of_model(model: dict) -> list:
    '''Returns input pins of model'''
    if 'InputPins' not in model['Properties'].keys():
        return []
    return model['Properties']['InputPins']

def get_output_pins_of_model(model: dict) -> list:
    '''Returns output pins of model'''
    if 'OutputPins' not in model['Properties'].keys():
        return []
    return model['Properties']['OutputPins']

def get_model_with_input_pin(input_pin_id: str, models: list) -> dict:
    '''Returns model with input pin with input_pin_id'''
    for model in models:
        input_pins = get_input_pins_of_model(model)
        for input_pin in input_pins:
            if input_pin['Id'] == input_pin_id:
                return model
    return None

def get_models_with_parent(parent_id: str, models: dict) -> list:
    '''Returns all models that have parent_id as a parent'''
    child_models = []
    for model in models:
        if model['Properties']['Parent'] == parent_id:
            child_models.append(model)
    return child_models

def get_target_of_pin_recursively(output_pin: dict, models: dict, input_pins: set, output_pins: set) -> str:
    '''The target of an output pin may be another output pin (if FlowFragment is last element in another FlowFragment).
    This function goes from an output pin to its target until the target is an input pin and returns its owner id'''

    # if the output pin has no connections, it is the end of the game.
    if 'Connections' not in output_pin.keys():
        return None
    target_pin_id = output_pin['Connections'][0]['TargetPin']
    if target_pin_id in input_pins:
        next_pin = get_input_pin_with_id(target_pin_id, models)
        return next_pin['Owner']
    elif target_pin_id in output_pins:
        next_pin = get_output_pin_with_id(target_pin_id, models)
        return get_target_of_pin_recursively(next_pin, models, input_pins, output_pins)
    else:
        raise ValueError(f'target_pin_id {target_pin_id} neither in input_pins nor in output_pins')

def get_input_pin_with_id(input_pin_id: str, models: dict, model: dict = None) -> dict:
    '''Returns input pin with input_pin_id, None, if none found.
    If model is given, only looks for input pins in that model.'''
    if model != None:
        for input_pin in model['Properties']['InputPins']:
            if input_pin['Id'] == input_pin_id:
                return input_pin
        return None
    # if no model was given as a parameter
    for model in models:
        for input_pin in model['Properties']['InputPins']:
            if input_pin['Id'] == input_pin_id:
                return input_pin
    return None

def get_output_pin_with_id(output_pin_id: str, models: dict, model: dict = None) -> dict:
    '''Returns output pin with id output_pin_id, None, if none found.
    If model is given, only looks for output pins in that model.'''
    if model != None:
        for output_pin in model['Properties']['OutputPins']:
            if output_pin['Id'] == output_pin_id:
                return output_pin
        return None
    # if no model was given as a parameter
    for model in models:
        for output_pin in model['Properties']['OutputPins']:
            if output_pin['Id'] == output_pin_id:
                return output_pin
    return None

def convert_condition_from_articy_to_python(text: str) -> str:
    # shamelessly stolen from https://github.com/TheSchnappi/articy2renpy/blob/master/main.py#L53
    converted_text = text.replace("true", "True")
    converted_text = converted_text.replace("false", "False")
    converted_text = converted_text.replace("&&", "and")
    converted_text = converted_text.replace("||", "or")
    # Regex replacement for "!" into "not", without killing "!="
    regex_match = True
    while regex_match:
        regex_match = re.search("![^=]", converted_text)
        if regex_match:
            regex_index = regex_match.start()
            converted_text = converted_text[:regex_index] + "not " + converted_text[regex_index + 1:]
    return converted_text.strip()

def add_escape_characters(text: str) -> str:
    '''Adds escape characters to the following characters: " and ' and %
    See https://www.renpy.org/doc/html/text.html#escape-characters for more details'''
    text = text.replace(r'"', r'\"')
    text = text.replace(r"'", r"\'")
    text = text.replace(r"%", r"\%")
    return text

def remove_problematic_letters(text: str) -> str:
    '''Removes double and single quotation marks'''
    text = text.replace('"', '')
    text = text.replace("'", '')
    return text

def contains_img_call(line: str) -> bool:
    '''Determines whether the given line contains an image call'''
    if '{' not in line:
        return False
    line = line.lower()
    img_file_types = ['.png', '.webp', '.gif', '.jpg', '.jpeg']
    for file_type in img_file_types:
        if f'{file_type}}}' in line:
            return True
    
    return False

def get_choice_text(model: dict, connection: dict) -> str:
    '''Returns the choice text for a connection with model as the target.
    If the model has a MenuText, then that will be returned.
    If not, then the label of the connection will be returned.
    If that is also not set, then the Text of the model will be returned.'''
    if 'MenuText' in model['Properties'] and model['Properties']['MenuText'] != '':
        return model['Properties']['MenuText']
    elif connection['Label'] != '':
        return connection['Label']
    else:
        return model['Properties']['Text']
    
def get_free_character_name(character_name: str, entity_id_to_character_name_map: dict) -> str:
    '''Returns a character name that is not yet in character_name_to_entity_id_map'''
    if character_name not in entity_id_to_character_name_map.values():
        return character_name
    count = 1
    while True:
        if f'{character_name}_{count}' not in entity_id_to_character_name_map.values():
            return f'{character_name}_{count}'
        else:
            count += 1

def get_connection_index(connection: dict, models: dict) -> int:
    '''Returns the index of the connection by getting the index of the target model'''
    choice_id = connection['Target']
    choice_model = get_model_with_id(choice_id, models)
    index = get_choice_index(choice_model)
    return index

def get_template_display_name_by_type(type_str: str, object_definitions: list) -> str:
    '''Returns the DisplayName attribute of a template by its type'''
    # because of course type and display name are not the same
    for obj in object_definitions:
        if obj["Type"] != type_str:
            continue
        return obj["Template"]["DisplayName"]
    return None

def get_choice_index(model: dict, index_default_value: int = 1904) -> int:
    '''Returns the index of the choice which is in Properties>StageDirections.
    The stage directions are separated by ,
    This function will return all numbers of the first direction that contains
    numbers.
    If there is no index value in the stage directions then the function
    will return index_default_value + the ID of the model 
    which should be some nice high number'''

    if 'StageDirections' not in model['Properties']:
        id_value = int(model['Properties']['Id'], 0)  # automatically detect format and convert to int 
        return index_default_value + id_value
    stage_directions = str(model['Properties']['StageDirections'])
    # if there are no stage directions, no index was given
    if stage_directions == "":
        return index_default_value
    stage_directions = string_to_list(stage_directions, separator=",")
    for stage_direction in stage_directions:
        try:
            index = int(stage_direction)
            return index
        except ValueError:
            pass
    
    id_value = int(model['Properties']['Id'], 0) # automatically detect format and convert to int 
    return index_default_value + id_value

def has_stage_direction(model: dict, attribute: str) -> bool:
    '''Whether a model has a specific attribute in its stage directions.
    Returns False if model has no stage directions.'''
    if 'StageDirections' not in model['Properties']:
        return False
    stage_directions = model['Properties']['StageDirections']
    stage_directions = string_to_list(stage_directions, separator=",")
    for stage_direction in stage_directions:
        # remove spaces
        stage_direction = stage_direction.replace(" ", "")
        if stage_direction == attribute:
            return True
    return False

def get_substr_between(text: str, left: str, right: str) -> str:
    '''Returns the substring of text between left and right'''
    index_left = text.find(left)
    index_right= text.find(right, index_left + len(left))
    if index_left == -1 or index_right == -1:
        return None
    index_left = index_left + len(left)
    return text[index_left : index_right]

def get_speaker_name(model: dict, entity_id_to_character_name_map: dict) -> str:
    '''Returns the speaker of the given model, empty string if none'''
    speaker_name = ''
    speaker_id = model['Properties']['Speaker']
    if speaker_id in entity_id_to_character_name_map.keys():
        speaker_name = entity_id_to_character_name_map[speaker_id]
    stage_directions = model['Properties']['StageDirections']
    stage_directions_speaker = get_substr_between(stage_directions, 'speaker="', '"')
    if stage_directions_speaker:
        speaker_name = '"' + stage_directions_speaker + '"'
    return speaker_name

def get_label(model: dict, label_prefix="label_") -> str:
    '''Returns the label of the given model'''
    # Check if label was given via stage directions
    if 'StageDirections' in model['Properties']:
        stage_directions = model['Properties']['StageDirections']
        stage_directions_label = get_substr_between(stage_directions, 'label="', '"')
        if stage_directions_label is not None:
            return stage_directions_label
    
    # If not stage directions, then make label with with label_prefix and model_id
    model_id = model['Properties']['Id']
    return f'{label_prefix}{model_id}'

def lines_of_model_text(model: dict, markdown_text_styles: bool, separator: str = "\r\n\r\n", text_attr: str = "Text") -> list:
    '''Returns the lines of model text as list of strings.
    markdown_text_styles specifies whether Markdown commands for italic, bold and underlined text shall be parsed.

    text_attr is the key of the text that shall be returned. It should be one of the following:
     - "Text" (default)
     - "MenuText"
     - "StageDirections"
    '''
    model_text = model['Properties'][text_attr]
    model_text = preprocess_text(model_text, markdown_text_styles)
    model_text_lines = model_text.split(separator)
    return model_text_lines

def text_style_markdown_to_renpy(text:str) -> str:
    '''Replaces Markdown text style commands with RenPy commands.
    
    Replaces:
     - **text** with {b}text{/b}
     - *text* with {i}text{/i}
     - _text_ with {u}text{/u}
    '''
    text = re.sub(r'\*\*(.*?)\*\*', r'{b}\1{/b}', text)
    text = re.sub(r'\*(.*?)\*', r'{i}\1{/i}', text)
    text = re.sub(r'_(.*?)_', r'{u}\1{/u}', text)
    return text

def add_renpy_text_style_commands(text: str) -> str:
    '''Adds RenPy commands for italic, bold and underlined text but only for text that is not in square brackets i.e. in [].
    
    Replaces:
     - **text** with {b}text{/b}
     - *text* with {i}text{/i}
     - _text_ with {u}text{/u}
    '''

    # text in [] should not be changed, e.g. [player_character.fake_name] shall remain the same.
    # split whole text into parts. A part is either text in [] (including []) or text outside of [] (excluding [])
    # substitute characters only for text outside []
    # Eventually, combine all parts to one final text and return it
    remaining_text = text
    unchanged_text_parts = []
    changeable_text_parts = []
    while remaining_text != "":
        substr = get_substr_between(remaining_text, "[", "]")
        if substr == None:
            changeable_text_parts.append(remaining_text)
            break

        substr = "[" + substr + "]"
        substr_index = remaining_text.find(substr)
        substr_len = len(substr)
        changeable_text_part = remaining_text[:substr_index]
        changeable_text_parts.append(changeable_text_part)
        unchanged_text_parts.append(substr)
        remaining_text = remaining_text[substr_index+substr_len:]

        if remaining_text == "":
            changeable_text_parts.append("")

    final_text = ""
    for index_part in range(len(changeable_text_parts) -1):
        formatted_text = text_style_markdown_to_renpy(changeable_text_parts[index_part])
        raw_text_part = unchanged_text_parts[index_part]
        final_text = final_text + formatted_text + raw_text_part
    
    # there is one changeable part more than unchanged text part
    formatted_text = text_style_markdown_to_renpy(changeable_text_parts[-1])
    final_text = final_text + formatted_text
    
    return final_text

def preprocess_text(text: str, markdown_text_styles: bool) -> str:
    '''Preprocesses the given text. Adds escape characters and -if specified- parses simple markdown commands.'''
    text = add_escape_characters(text)
    if markdown_text_styles:
        text = add_renpy_text_style_commands(text)
    return text

def string_to_list(string: str, separator=",") -> list[str]:
    '''Converts string to a list by splitting it by the given separator.
    Empty strings will be omitted.'''
    return [x.strip() for x in string.split(separator) if x.strip()]

def text_starts_with(text: str, beginnings: list[str], lower: bool = True) -> bool:
    '''Whether text starts with one of the strings in beginnings.
    Everything is converted to lower case by default.'''
    if lower:
        text = text.lower()
        beginnings = [beginning.lower() for beginning in beginnings]
    for beginning in beginnings:
        if text.startswith(beginning):
            return True
    return False

class UnexpectedContentException(Exception):
    "Raised when contents of a directory are unexpected"
    pass

class InvalidArticy(Exception):
    "Raised when articy structure cannot be parsed to RenPy"
    pass
