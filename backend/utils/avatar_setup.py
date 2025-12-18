import json
from .llm_tooling import LLM
from utils import prepare_query_engines



llm_choice = 'gpt-4' #'mistral-large-instruct' #"gemma-3-27b-it"


# In-memory storage (replace with DB later if you like)
avatars_path = '../avatars.json'
avatars = json.load(open(avatars_path, 'r'))

avatar_llms = {}
avatar_rag_tools = {}

for avatar in avatars:
    avatar_id = avatar['id']
    avatar_llms[avatar_id] = LLM(
                        provider="openai",
                        openai_api_key=API_KEY,          # or via env var OPENAI_API_KEY
                        openai_model=llm_choice, #"gpt-4.1-mini",      # or "gpt-4.1" / whatever you want
                        system_prompt= open('../avatars_context/'+avatar_id+'/prompt','r').read() 

                    )
    avatar_rag_tools[avatar_id] = prepare_query_engines(avatar_id=avatar['id'], drive_folder_id=avatar['driveFolderId'])


# vector_query_llm, _ = get_llm('gwdg', llm_choice, system_prompt= 'Provide an accurate response to the given query.:')

text_query_llm, _ = LLM(
                    provider="openai",
                    openai_api_key=API_KEY,          # or via env var OPENAI_API_KEY
                    openai_model=llm_choice, #"gpt-4.1-mini",      # or "gpt-4.1" / whatever you want
                    system_prompt="Context is needed to address the most recent message in this conversation (NOTE: EMPHASIS ON THE USER\'S LAST MESSAGE. INFO IS NEEDED TO RESPOND TO THE USER\'S LAST MESSAGE) (Or maybe not. Look through the given conversation and determine. If not, your query could just be "General information about the Lahn"). Return a one-line string containing 6 total keywords, each separated by a comma and space: 3 relevant English keywords  (to be queried in the database) that aim to extract the needed context, a "|" divider, and another 3 keywords corresponding to the German translations of the earlier keywords. Your job is not to predict what any party will say, but to return these keywords, so they can be used to extract information relevant for the concerned party to make their decision. That is where your job stops. Reply only with the keywords and nothing else (not even "keywords:"). The keywords should be only relevant to the most recent message, since that is what context is needed on. Double-check that your response is in the format "keyword1, keyword2, keyword3 | keyword1translation, keyword2translation, keyword3translation", with the keywords being only relevant to the last message: ",
                )


# get_llm('gwdg', llm_choice, system_prompt= 'Context is needed to address the most recent message in this conversation (NOTE: EMPHASIS ON THE USER\'S LAST MESSAGE. INFO IS NEEDED TO RESPOND TO THE USER\'S LAST MESSAGE) (Or maybe not. Look through the given conversation and determine. If not, your query could just be "General information about the Lahn"). Return a one-line string containing 6 total keywords, each separated by a comma and space: 3 relevant English keywords  (to be queried in the database) that aim to extract the needed context, a "|" divider, and another 3 keywords corresponding to the German translations of the earlier keywords. Your job is not to predict what any party will say, but to return these keywords, so they can be used to extract information relevant for the concerned party to make their decision. That is where your job stops. Reply only with the keywords and nothing else (not even "keywords:"). The keywords should be only relevant to the most recent message, since that is what context is needed on. Double-check that your response is in the format "keyword1, keyword2, keyword3 | keyword1translation, keyword2translation, keyword3translation", with the keywords being only relevant to the last message: ')
#This should be a very technically capable model, to cut down the chances of buggy-code-related issues.
sensor_query_llm, _ = LLM(
                    provider="openai",
                    openai_api_key=API_KEY,          # or via env var OPENAI_API_KEY
                    openai_model=llm_choice, #"gpt-4.1-mini",      # or "gpt-4.1" / whatever you want
                    system_prompt="Provide an accurate response to the given query. Only perform calculations. Do not generate any plots or visualizations. Always include the following setup **before any resampling or time-based operations**: df[\'created_at\'] = pd.to_datetime(df[\'created_at\'])  df = df.set_index(\'created_at\') . When calculating the variation of a quantity over an interval, use the largest of [seconds, minutes, hours,days, weeks,months,years] which is smaller than the range you\'re calculating over. For example, \'How has X varied over the past week?\' should be based on a daily interval. \'How has Y varied over the past year?\' on a monthly interval etc. :",
                )

# get_llm('gwdg', 'mistral-large-instruct', system_prompt= 'Provide an accurate response to the given query. Only perform calculations. Do not generate any plots or visualizations. Always include the following setup **before any resampling or time-based operations**: df[\'created_at\'] = pd.to_datetime(df[\'created_at\'])  df = df.set_index(\'created_at\') . When calculating the variation of a quantity over an interval, use the largest of [seconds, minutes, hours,days, weeks,months,years] which is smaller than the range you\'re calculating over. For example, \'How has X varied over the past week?\' should be based on a daily interval. \'How has Y varied over the past year?\' on a monthly interval etc. :')
# mistral-large-instruct qwen2.5-coder-32b-instruct