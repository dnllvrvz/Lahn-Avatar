import os, json
from dotenv import load_dotenv

from .llm_tooling import LLM
from .utils import prepare_query_engines, SensorsTool, fetch_system_prompt_from_gdoc


load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY") #("GWDG_API_KEY")
API_BASE = None #os.getenv("GWDG_API_BASE")


llm_choice = 'gpt-4.1-mini' #'gpt-4' #'mistral-large-instruct' #"gemma-3-27b-it"


# vector_query_llm, _ = get_llm('gwdg', llm_choice, system_prompt= 'Provide an accurate response to the given query.:')

# LLM for sensor data analysis
sensor_query_llm = LLM(
                    provider="openai",
                    openai_api_key=API_KEY,
                    openai_model=llm_choice,
                    system_prompt='Provide an accurate response to the given query. Only perform calculations. Do not generate any plots or visualizations. Always include the following setup **before any resampling or time-based operations**: df[\'created_at\'] = pd.to_datetime(df[\'created_at\');  df = df.set_index(\'created_at\') . When calculating the variation of a quantity over an interval, use the largest of [seconds, minutes, hours,days, weeks,months,years] which is smaller than the range you\'re calculating over. For example, \'How has X varied over the past week?\' should be based on a daily interval. \'How has Y varied over the past year?\' on a monthly interval etc. :')

text_query_llm = LLM(
                    provider="openai",
                    openai_api_key=API_KEY,          # or via env var OPENAI_API_KEY
                    openai_model=llm_choice, #"gpt-4.1-mini",      # or "gpt-4.1" / whatever you want
                    system_prompt='Context is needed to address the most recent message in the conversation (NOTE: EMPHASIS ON THE USER\'S LAST MESSAGE. INFO IS NEEDED TO RESPOND TO THE USER\'S LAST MESSAGE) (Or maybe not. Look through the given conversation and determine. If not, your query could just be "General information about the Lahn"). Return a one-line string containing 6 total keywords, each separated by a comma and space: 3 relevant English keywords  (to be queried in the database) that aim to extract the needed context, a "|" divider, and another 3 keywords corresponding to the German translations of the earlier keywords. Your job is not to predict what any party will say, but to return these keywords, so they can be used to extract information relevant for the concerned party to make their decision. That is where your job stops. Reply only with the keywords and nothing else (not even "keywords:"). The keywords should be only relevant to the most recent message, since that is what context is needed on. Double-check that your response is in the format "keyword1, keyword2, keyword3 | keyword1translation, keyword2translation, keyword3translation", with the keywords being only relevant to the last message: :')


# get_llm('gwdg', llm_choice, system_prompt= 'Provide an accurate response to the given query. Only perform calculations. Do not generate any plots or visualizations. Always include the following setup **before any resampling or time-based operations**: df[\'created_at\'] = pd.to_datetime(df[\'created_at\'])  df = df.set_index(\'created_at\') . When calculating the variation of a quantity over an interval, use the largest of [seconds, minutes, hours,days, weeks,months,years] which is smaller than the range you\'re calculating over. For example, \'How has X varied over the past week?\' should be based on a daily interval. \'How has Y varied over the past year?\' on a monthly interval etc. :')
# mistral-large-instruct qwen2.5-coder-32b-instruct

class AvatarConfig:
    def __init__(self, system_prompt):
        self.system_prompt = system_prompt

def generate_avatars_config(specific_avatar_id=None):
	global avatars_path, avatar_llms, avatar_rag_tools, avatar_sensor_tools
	# In-memory storage (replace with DB later if you like)
	avatars_path = 'avatars.json'
	avatars = json.load(open(avatars_path, 'r'))

	if specific_avatar_id is None:
		avatar_llms = {}
		avatar_rag_tools = {}
		avatar_sensor_tools = {}  # Already declared global
		avatars_to_process = avatars
	else:
		# If we are refreshing a single avatar, we don't want to wipe the existing dicts
		avatars_to_process = [a for a in avatars if a['id'] == specific_avatar_id]
		if not avatars_to_process:
			return None, None, None # Avatar not found

	for avatar in avatars_to_process:
		avatar_id = avatar['id']
		print('\nWorking on Avatar: ', avatar_id)
		try:
			system_prompt = open('avatars_context/'+avatar_id+'/prompt/system_prompt.txt','r').read()
		except FileNotFoundError:
			print('System prompt not found for avatar ' + avatar_id + '. Fetching from G-Doc...')
			if avatar.get('systemPromptUrl'):
				fetch_system_prompt_from_gdoc(avatar_id, avatar['systemPromptUrl'])
				system_prompt = open('avatars_context/'+avatar_id+'/prompt/system_prompt.txt','r').read()
			else:
				system_prompt = "Default system prompt." # Or handle error appropriately

		avatar_config = AvatarConfig(system_prompt=system_prompt)

		# Get RAG languages with backward compatibility
		rag_languages = avatar.get('ragLanguages', ['en', 'de'])
		print(f"Avatar {avatar_id} RAG languages: {rag_languages}")

		rag_tools = prepare_query_engines(avatar_id=avatar_id, drive_folder_id=avatar.get('driveFolderId'), rag_languages=rag_languages)

		# Create sensor tool for this avatar if it has a sensor API URL
		sensor_api_url = avatar.get('sensorApiUrl', '').strip()
		sensor_description = avatar.get('sensorDescription', '').strip()

		if sensor_api_url:
			print(f"Creating sensor tool for avatar {avatar_id}")
			avatar_sensor_tools[avatar_id] = SensorsTool(
				sensor_query_llm,
				sensor_url=sensor_api_url,
				sensor_description=sensor_description if sensor_description else None
			)
		else:
			print(f"No sensor API URL for avatar {avatar_id}")
			avatar_sensor_tools[avatar_id] = None

		if specific_avatar_id:
			avatar_llms[avatar_id] = avatar_config
			avatar_rag_tools[avatar_id] = rag_tools
			avatar_sensor_tools[avatar_id] = avatar_sensor_tools[avatar_id]
			return avatar_config, rag_tools, avatar_sensor_tools

		avatar_llms[avatar_id] = avatar_config
		avatar_rag_tools[avatar_id] = rag_tools
		avatar_sensor_tools[avatar_id] = avatar_sensor_tools[avatar_id]

	return avatar_llms, avatar_rag_tools, avatar_sensor_tools


avatar_llms, avatar_rag_tools, avatar_sensor_tools = generate_avatars_config()
