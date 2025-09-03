# dump_token.py
import pickle
creds = pickle.load(open("tokens/demo_google.pkl", "rb"))
print(creds.token)
