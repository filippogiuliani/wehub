// Privacy notice texts, one entry per language: a draft banner, sections [title, html] and the "last updated" line.
// DRAFT: for a private family instance this is mostly a formality; if you open the app to others, complete the
// fields in [SQUARE BRACKETS] and have it reviewed. The html strings are written by the developers only (never user input).
export default {
  it: {
    draft: 'Bozza – da completare prima di aprire l\'app ad altre persone.',
    sections: [
      ['Titolare del trattamento', '[NOME], [INDIRIZZO], email: [EMAIL DI CONTATTO].'],
      ['Quali dati trattiamo', "Nome, email e identificativo di accesso dei membri della famiglia; nome, data di nascita e tipo (adulto o bambino) delle persone che l'amministratore inserisce; a quali app ciascuno può accedere."],
      ['Perché li trattiamo', "Per permettere un accesso unico alle app della famiglia (doTrack, eaTrack, paTrack) e far loro conoscere chi fa parte della famiglia. Le app ricevono solo questi dati, non il contrario. Non vendiamo i dati e non li usiamo per pubblicità."],
      ['Dove sono conservati e per quanto', "Sul server [DOVE], con copie di sicurezza in [DOVE SONO I BACKUP]. L'accesso avviene tramite [POCKET ID / PROVIDER]. I dati restano finché sei nella famiglia; quando vieni tolto, il tuo account resta finché non chiedi di cancellarlo."],
      ['I tuoi diritti', "Puoi correggere i tuoi dati, chiedere la cancellazione, revocare il consenso e presentare reclamo al Garante per la protezione dei dati personali. Per qualsiasi richiesta: [EMAIL DI CONTATTO]."],
      ['Cookie', 'Usiamo un solo cookie tecnico per mantenerti collegato. Nessun cookie di profilazione o di terze parti.'],
    ],
    updated: 'Ultimo aggiornamento: [DATA]',
  },
  en: {
    draft: 'Draft – to be completed before opening the app to other people.',
    sections: [
      ['Data controller', '[NAME], [ADDRESS], email: [CONTACT EMAIL].'],
      ['What data we process', 'Name, email and sign-in identifier of the family members; name, date of birth and kind (adult or child) of the people the admin adds; which apps each one may use.'],
      ['Why we process it', 'To give one sign-in to the family apps (doTrack, eaTrack, paTrack) and let them know who is in the family. The apps receive only this data. We do not sell data or use it for advertising.'],
      ['Where it is stored and for how long', 'On the server [WHERE], with backups at [WHERE BACKUPS ARE]. Sign-in goes through [POCKET ID / PROVIDER]. Data is kept while you are in the family; when you are removed, your account stays until you ask for it to be deleted.'],
      ['Your rights', 'You can correct your data, ask for deletion, withdraw consent and lodge a complaint with your data protection authority. For any request: [CONTACT EMAIL].'],
      ['Cookies', 'We use a single technical cookie to keep you signed in. No profiling or third-party cookies.'],
    ],
    updated: 'Last updated: [DATE]',
  },
};
