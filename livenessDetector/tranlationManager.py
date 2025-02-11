import os
import json

class TranslationManager:
    def __init__(self, locale='en', locales_dir='locales'):
        self.locales_dir = locales_dir
        if locale==None:
            locale = 'en'
        self.locale = locale
        self.locale_not_found = False  # Flag for missing locales_dir
        self.translations = self.load_translations(locale)

    def load_translations(self, locale):
        parts = locale.split('_')
        try:
            # Attempt to load the specific locale
            return self._load_locale_file(locale)
        except FileNotFoundError:
            # If specific locale is not found, try the parent locale
            if len(parts) > 1:
                try:
                    return self._load_locale_file(parts[0])
                except FileNotFoundError:
                    print("Warning, Locale Part not found:", locale)
            # If parent locale is not found, use the default
            try:
                return self._load_locale_file('default')
            except FileNotFoundError:
                self.locale_not_found = True
                print("Warning, Locale not found:", locale)
                return {}  # Empty dict means no translations available

    def _load_locale_file(self, locale_name):
        #print("load_local_file:", locale_name)
        #if not os.path.exists(self.locales_dir):
        #    raise Exception(f"Locales directory '{self.locales_dir}' does not exist.")
        with open(os.path.join(self.locales_dir, f'{locale_name}.json'), 'r') as f:
            return json.load(f)

    def translate(self, key):
        if self.locale_not_found:
            return key  # Return the key directly if locales_dir was not found

        keys = key.split('.')
        translation_value = self.translations
        try:
            for k in keys:
                translation_value = translation_value[k]
            return translation_value
        except KeyError:
            return key  # Return the key if the translation is not found
