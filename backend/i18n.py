"""Server-side translations: error messages and emails.
Source texts are in English; Italian translations below."""
import re

from flask import g, has_request_context, request

LANGUAGES = ['it', 'en']
DEFAULT = 'it'


def normalize(value):
    v = str(value or '').lower()[:2]
    return v if v in LANGUAGES else None


def language():
    """Request language: user profile > X-Language header (from the frontend) > Accept-Language > default."""
    if not has_request_context():
        return DEFAULT
    user = getattr(g, 'user', None)
    if user and normalize(user.get('language')):
        return user['language']
    return (normalize(request.headers.get('X-Language'))
            or request.accept_languages.best_match(LANGUAGES)
            or DEFAULT)


IT = {
    'To sign up you must accept the privacy notice': "Per registrarti devi accettare l'informativa privacy",
    "You're the only member: to delete the family, delete your account": "Sei l'unico membro: per eliminare la famiglia elimina l'account",
    'Sign in or sign up to accept': 'Accedi o registrati per accettare',
    'Sign-in failed, please try again': 'Accesso non riuscito, riprova',
    'Sign-in required': 'Accesso richiesto',
    'Sign-up expired: please try again': 'Registrazione scaduta: riprova',
    'Invalid email': 'Email non valida',
    'Wrong email or password': 'Email o password errati',
    'An account with this email already exists': 'Esiste già un account con questa email',
    'Family not found': 'Famiglia non trovata',
    'Name is required': 'Il nome è obbligatorio',
    'The provider did not return an identifier': 'Il provider non ha fornito un identificativo',
    'The provider did not return a verified email address': 'Il provider non ha fornito un indirizzo email verificato',
    "Set a password first, otherwise you couldn't sign in anymore": 'Imposta prima una password, altrimenti non potresti più accedere',
    'Invalid or expired invitation': 'Invito non valido o scaduto',
    'Sign-up is by invitation only': 'La registrazione è possibile solo su invito',
    'Invalid or expired link': 'Link non valido o scaduto',
    'Member not found': 'Membro non trovato',
    'No file uploaded': 'Nessun file caricato',
    'No family associated': 'Nessuna famiglia associata',
    'No sign-up in progress': 'Nessuna registrazione in corso',
    'Origin not allowed': 'Origine non consentita',
    'Current password is wrong': 'Password attuale errata',
    'Password too long': 'Password troppo lunga',
    'Provider not configured': 'Provider non configurato',
    'This account is already linked to another user': 'Questo account è già collegato a un altro utente',
    'Only the family admin can do this': "Solo l'amministratore della famiglia può farlo",
    'Too many attempts, try again in a few minutes': 'Troppi tentativi, riprova tra qualche minuto',
    'Type your email to confirm': 'Scrivi la tua email per confermare',
    'Invalid request (JSON expected)': 'Richiesta non valida (atteso JSON)',
    'invalid family_id': 'family_id non valido',
    "{name}'s family": 'Famiglia di {name}',
    # Family
    'Too many links': 'Troppi collegamenti',
    'Link not found': 'Collegamento non trovato',
    'Invalid address': 'Indirizzo non valido',
    'Invalid members': 'Membri non validi',
    'Choose who sees it': 'Scegli chi lo vede',
    'There is already someone with this name': "C'è già qualcuno con questo nome",
    'Too many people': 'Troppe persone',
    'Person not found': 'Persona non trovata',
    'A member is removed from the members': 'Un membro si toglie dai membri',
    'Already in the family': 'È già nella famiglia',
    'Invalid apps': 'App non valide',
    'Invalid role': 'Ruolo non valido',
    'The family needs at least one admin': 'La famiglia deve avere almeno un amministratore',
    "You're the only member of the family": "Sei l'unico membro della famiglia",
    'Ask the family admin to add you in weHub': "Chiedi all'amministratore della famiglia di aggiungerti in weHub",
    'Invalid request': 'Richiesta non valida',
    'Sign-in with a password is disabled: use one of the providers': "L'accesso con password è disattivato: usa uno dei provider",
    'Sign-up with a password is disabled: use one of the providers': 'La registrazione con password è disattivata: usa uno dei provider',
    'date': 'data', 'birth_date': 'data di nascita',
}

IT_PATTERNS = [
    (r'^Password must be at least (\d+) characters$', r'La password deve avere almeno \1 caratteri'),
    (r'^(.+): invalid date$', r'\1: data non valida'),
    (r'^(.+): invalid time$', r'\1: ora non valida'),
]

MESSAGES = {'it': (IT, IT_PATTERNS)}


def tr(text, lang=None, **values):
    lang = lang or language()
    if lang in MESSAGES:
        dictionary, patterns = MESSAGES[lang]
        if text in dictionary:
            text = dictionary[text]
        else:
            for pattern, template in patterns:
                if m := re.match(pattern, text):
                    parts = [dictionary.get(p, p) for p in m.groups()]
                    text = re.sub(r'\\(\d)', lambda ref: parts[int(ref.group(1)) - 1], template)
                    break
    return text.format(**values) if values else text


EMAILS = {
    'verify': {
        'it': ('Conferma il tuo indirizzo email – weHub',
               'Ciao!\n\nConferma il tuo indirizzo email aprendo questo link:\n{link}\n\n'
               'Il link vale 3 giorni. Se non ti sei registrato su weHub ignora questo messaggio.'),
        'en': ('Confirm your email address – weHub',
               'Hi!\n\nConfirm your email address by opening this link:\n{link}\n\n'
               "The link is valid for 3 days. If you didn't sign up for weHub, ignore this message."),
    },
    'reset': {
        'it': ('Reimposta la password – weHub',
               'Per scegliere una nuova password apri questo link (vale 2 ore):\n{link}\n\n'
               'Se non hai chiesto tu il cambio password ignora questo messaggio.'),
        'en': ('Reset your password – weHub',
               'To choose a new password open this link (valid for 2 hours):\n{link}\n\n'
               "If you didn't request a password change, ignore this message."),
    },
}


def email(kind, lang, **values):
    subject, text = EMAILS[kind].get(lang) or EMAILS[kind][DEFAULT]
    return subject.format(**values), text.format(**values)
