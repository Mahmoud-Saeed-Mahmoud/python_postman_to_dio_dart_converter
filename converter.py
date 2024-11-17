import json
import os
import re
import requests  # For making HTTP requests
from urllib.parse import urlencode


def snake_case(name):
    """Convert a string to snake_case."""
    name = re.sub(r'[\W_]+', ' ', name)  # Replace non-alphanumeric characters with space
    return '_'.join(name.lower().split())

def upper_camel_case(name):
    """Convert a string to UpperCamelCase."""
    return ''.join(word.title() for word in name.split()).replace('_', '')
def lower_camel_case(name):
    """Convert a string to lowerCamelCase."""
    if not name:  # Check if the name is empty
        return name  # Return the input name if it's empty

    # Convert the name into camel case (first letter of each word capitalized, except the first word)
    name = ''.join(word.title() for word in name.split())

    # Make the first character lowercase, and remove underscores
    return (name[0].lower() + name[1:]).replace('_', '')


def extract_variables(text):
    """Extract variables from the {{...}} placeholders in a string."""
    return re.findall(r'\{\{(.*?)\}\}', text)

def contains_placeholder(text):
    """Check if the string contains the pattern '{{...}}'."""
    pattern = r'\{\{(.*?)\}\}'
    return bool(re.search(pattern, text))

def replace_url_variables(url):
    """Replace {{...}} placeholders in the URL with Dart variable syntax."""
    return re.sub(r'\{\{(.*?)\}\}', lambda match: f"${match.group(1)}/", url)

def replace_header_variables(value):
    """Replace {{...}} placeholders in header values with Dart variable syntax (no '/')."""
    return re.sub(r'\{\{(.*?)\}\}', lambda match: f"${lower_camel_case(match.group(1))}", value)

def handle_path_parameters(url, path):
    """Detect dynamic path parameters in the URL and replace them with Dart variables."""
    path_variables = []
    updated_url = url
    for i, segment in enumerate(path):
        if re.match(r'^[a-f0-9]{24,}$', segment):  # UUID-like pattern
            param_name = 'id' if i == len(path) - 1 else f"param{i}"
            updated_url = updated_url.replace(segment, f"${param_name}")
            path_variables.append(lower_camel_case(param_name))
        elif re.match(r'^\d+$', segment):  # Numeric path segment
            param_name = 'id' if i == len(path) - 1 else f"param{i}"
            updated_url = updated_url.replace(segment, f"${param_name}")
            path_variables.append(lower_camel_case(param_name))
    return updated_url, path_variables

def generate_query_class(query_params, class_name):
    """Generate a Dart class for query parameters."""
    if not query_params:
        return ''

    # Parse the JSON query parameters into a dictionary
    try:
        query_content = query_params
    except json.JSONDecodeError as e:
        print(f"Invalid JSON query parameters: {e}")
        return ''

    class_code = f"class {class_name} {{\n"
    empty_lists = [key for key, value in query_content.items() if key =='']
    if empty_lists:
        for key in empty_lists:
            query_content.pop(key)
    # Generate fields based on the query structure
    for key, value in query_content.items():
        dart_type = "dynamic"  # Default type
        if isinstance(value, list):
            dart_type = "final List<dynamic>?"  # Handle arrays as nullable dynamic lists
        elif isinstance(value, bool):
            dart_type = "final bool?"
        elif isinstance(value, int):
            dart_type = "final int?"
        elif isinstance(value, float):
            dart_type = "final double?"
        elif isinstance(value, str):
            if value == "true" or value == "false":
                dart_type = "final bool?"
            elif value.isdigit():
                    dart_type = "final int?"
            elif value.replace('.', '').isdigit():
                    dart_type = "final double?"
            else:
                dart_type = "final String?"

        class_code += f"  {dart_type} {key};\n"

    # Generate constructor
    constructor_args = ', '.join(f"this.{key}" for key in query_content) + ","
    class_code += f"\n  const {class_name}({{{constructor_args}}});\n\n"

    # Generate `toMap` method for query parameters
    class_code += "  Map<String, dynamic> toMap() {\n"
    class_code += "    return {\n"
    for key in query_content:
        class_code += f"      if ({key} != null) '{key}': {key},\n"
    class_code += "    };\n  }\n"

    class_code += "}\n"
    return class_code



def generate_body_class(body_raw, class_name):
    """Generate a Dart class for body parameters."""
    if not body_raw:
        return ''

    # Parse the JSON body into a dictionary
    try:
        body_content = json.loads(body_raw)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON body: {e}")
        return ''

    class_code = f"class {class_name} {{\n"

    # Generate fields based on the JSON structure
    for key, value in body_content.items():
        if key == '':
            continue
        dart_type = "dynamic"  # Default type
        if isinstance(value, list):
            dart_type = "final List<dynamic>?"  # Handle arrays as nullable dynamic lists
        elif isinstance(value, bool):
            dart_type = "final bool?"
        elif isinstance(value, int):
            dart_type = "final int?"
        elif isinstance(value, float):
            dart_type = "final double?"
        elif isinstance(value, str):
            if value == "true" or value == "false":
                dart_type = "final bool?"
            elif value.isdigit():
                    dart_type = "final int?"
            elif value.replace('.', '').isdigit():
                    dart_type = "final double?"
            else:
                dart_type = "final String?"

        class_code += f"  {dart_type} {key};\n"

    # Generate constructor
    constructor_args = ', '.join(f"this.{key}" for key in body_content) + ","
    class_code += f"\n  const {class_name}({{{constructor_args}}});\n\n"

    # Generate `toJson` method
    class_code += "  Map<String, dynamic> toJson() {\n"
    class_code += "    return {\n"
    for key in body_content:
        class_code += f"      if ({key} != null) '{key}': {key},\n"
    class_code += "    };\n  }\n"

    class_code += "}\n"
    return class_code

def generate_dio_function(request_name, request):
    """Generate a Dart function for a given Postman request."""
    method = request['method'].lower()
    url = request['url']['raw']
    headers = request.get('header', [])
    body = request.get('body', None)
    auth = request.get('auth', None)

    # Remove query parameters from the URL
    url_without_query = re.split(r'\?', url)[0]

    # Extract the base URL including optional port
    base_url_match = re.match(r'^(https?://[a-zA-Z0-9.-]+(:[0-9]+)?)(/.*)?$', url_without_query)
    if base_url_match:
        base_url = base_url_match.group(1)  # Base URL (e.g., http://localhost:8080)
        endpoint = base_url_match.group(3) or ''  # Endpoint is the part after the base URL
    else:
        base_url = None
        endpoint = url_without_query  # If no match, treat the entire URL as the endpoint

    # Replace hardcoded base URL with `$baseUrl`
    dart_url = f"$baseUrl{endpoint}" if base_url else url_without_query

    # Handle dynamic path parameters
    path = request['url'].get('path', [])
    dart_url, path_parameters = handle_path_parameters(dart_url, path)

    # Extract query parameters from the original URL
    query_params = {param['key']: param['value'] for param in request['url'].get('query', [])}

    # Generate Dart class for query parameters
    query_params_class_code = ''
    if query_params:
        query_params_class_code = generate_query_class(query_params, upper_camel_case(request_name + '_query_params'))

    # Generate Dart class for body if present
    body_class_code = ''
    if body:
        body_raw = body.get('raw', '')  # Raw body data
        if body_raw:
            body_class_code = generate_body_class(body_raw, upper_camel_case(request_name + '_body'))

    # Extract all variables for the function signature
    url_variables = extract_variables(dart_url)
    header_variables = [
        extract_variables(header['value']) for header in headers if '{{' in header['value']]
    header_variables = [var for sublist in header_variables for var in sublist]  # Flatten list
    all_variables = set(url_variables + header_variables + path_parameters)

    # Convert all variables to lowerCamelCase for Dart function parameters
    dart_parameters = ', '.join([f"required String {lower_camel_case(var)}" for var in all_variables])

    # Add `baseUrl` as a required parameter
    if base_url:
        dart_parameters += ', required String baseUrl'

    # Add query parameters
    if query_params:
        dart_parameters += f', required {upper_camel_case(request_name + "_query_params")} {lower_camel_case(snake_case(request_name))}QueryParams'

    # Add body parameters
    if body_class_code:
        dart_parameters += f', required {upper_camel_case(request_name + "_body")} {lower_camel_case(snake_case(request_name))}Body'

    # Add accessToken if present
    if auth and auth.get('type') == 'bearer':
        dart_parameters += ', required String accessToken'

    # Generate the function
    function_name = lower_camel_case(request_name)
    dart_code = f"import 'package:dio/dio.dart';\n\n"
    if query_params:
        dart_code += f"import '{snake_case(request_name)}_query_params.dart';\n"
    if body_class_code:
        dart_code += f"import '{snake_case(request_name)}_body.dart';\n\n"
    dart_code += f"class {upper_camel_case(request_name)} {{\n"
    dart_code += f"  static Future<Response> {function_name}({{{dart_parameters}}}) async {{\n"
    dart_code += "    Dio dio = Dio();\n"

    # Add headers dynamically
    if headers:
        dart_code += "    dio.options.headers = {\n"
        for header in headers:
            header_value = header['value']
            if '{{' in header_value:
                key = header['key']
                dart_code += f"      '{key}': {replace_header_variables(header_value)},\n"
            else:
                dart_code += f"      '{header['key']}': '{header_value}',\n"
        dart_code += "    };\n"

    # Add authorization if present
    if auth and auth.get('type') == 'bearer':
        dart_code += f"    dio.options.headers['Authorization'] = 'Bearer $accessToken';\n"

    # Prepare the request call
    dart_code += f"    Response response = await dio.{method}(\n"
    dart_code += f"      '{dart_url}',\n"
    if query_params:
        dart_code += f"      queryParameters: {lower_camel_case(snake_case(request_name))}QueryParams.toMap(),\n"
    if body_class_code:
        dart_code += f"      data: {lower_camel_case(snake_case(request_name))}Body.toJson(),\n"
    dart_code += "    );\n\n"
    dart_code += "    print(response.data);\n\n"
    dart_code += "    return response;\n"
    dart_code += "  }\n}\n"

    # Generate filename and folder
    folder_name = snake_case(request_name)
    filename = f"{folder_name}.dart"
    return dart_code, folder_name, filename, query_params_class_code, body_class_code
def process_postman_collection(collection, output_dir):
    """Process the Postman collection and generate Dart files for each request."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for item in collection['item']:
        if 'item' in item:
            for subitem in item['item']:
                if 'item' in subitem:
                    for subsubitem in subitem['item']:
                        request_name = subsubitem['name'].replace('  ', ' ')  # Replace extra spaces
                        request = subsubitem['request']
                        dart_code, folder_name, filename, query_params_class_code, body_class_code = generate_dio_function(request_name, request)
                        request_folder = os.path.join(output_dir, folder_name)
                        if not os.path.exists(request_folder):
                            os.makedirs(request_folder)
                        with open(os.path.join(request_folder, filename), 'w') as f:
                            f.write(dart_code)
                        # Write queryParams class to file if present
                        if query_params_class_code:
                            with open(os.path.join(request_folder, f'{folder_name}_query_params.dart'), 'w') as f:
                                f.write(query_params_class_code)
                        # Write body class to file if present
                        if body_class_code:
                            with open(os.path.join(request_folder, f'{folder_name}_body.dart'), 'w') as f:
                                f.write(body_class_code)
                else:
                    request_name = subitem['name']
                    request = subitem['request']
                    dart_code, folder_name, filename, query_params_class_code, body_class_code = generate_dio_function(request_name, request)
                    request_folder = os.path.join(output_dir, folder_name)
                    if not os.path.exists(request_folder):
                        os.makedirs(request_folder)
                    with open(os.path.join(request_folder, filename), 'w') as f:
                        f.write(dart_code)
                    # Write queryParams class to file if present
                    if query_params_class_code:
                        with open(os.path.join(request_folder, f'{folder_name}_query_params.dart'), 'w') as f:
                            f.write(query_params_class_code)
                    # Write body class to file if present
                    if body_class_code:
                        with open(os.path.join(request_folder, f'{folder_name}_body.dart'), 'w') as f:
                            f.write(body_class_code)
        else:
            request_name = item['name']
            request = item['request']
            dart_code, folder_name, filename, query_params_class_code, body_class_code = generate_dio_function(request_name, request)
            request_folder = os.path.join(output_dir, folder_name)
            if not os.path.exists(request_folder):
                os.makedirs(request_folder)
            with open(os.path.join(request_folder, filename), 'w') as f:
                f.write(dart_code)
            # Write queryParams class to file if present
            if query_params_class_code:
                with open(os.path.join(request_folder, f'{folder_name}_query_params.dart'), 'w') as f:
                    f.write(query_params_class_code)
            # Write body class to file if present
            if body_class_code:
                with open(os.path.join(request_folder, f'{folder_name}_body.dart'), 'w') as f:
                    f.write(body_class_code)

# Load Postman collection from file
with open('postman_collection.json', 'r') as f:
    collection = json.load(f)

# Output directory for Dart files
output_directory = "generated_dart_requests"

# Generate Dart files
process_postman_collection(collection, output_directory)
