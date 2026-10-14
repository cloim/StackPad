"""Sign test clients in without Google: the engine trusts its own session store."""
import secrets

OWNER = 'owner@example.com'


def sign_in(app, client, email=OWNER, kind='browser', name=''):
    google = app.state.google
    if not google.owner:
        google._update(client_id='test.apps.googleusercontent.com', client_secret='secret', owner=email, allowed=[email])
    credential = secrets.token_urlsafe(32)
    app.state.sessions.create(credential, email, kind, name)
    client.cookies.set('stackpad_session', credential)
    return credential
