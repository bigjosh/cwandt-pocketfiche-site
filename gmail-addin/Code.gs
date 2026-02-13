var API_URL = 'https://pf.josh.com/upload/cgi-bin/app.py';
var UPLOAD_BASE_URL = 'https://pf.josh.com/upload/upload.html';
var PROP_ADMIN_ID = 'pf_admin_id';
var PROP_NOTES = 'pf_notes';
var PROP_NOTES_INITIALIZED = 'pf_notes_init';
var ADMIN_ID_MASK = '••••••••';

/**
 * Compose trigger — main UI. Shows ADMIN-ID, NOTES, TO recipient, and Insert button.
 */
function onComposeTrigger(e) {
  var props = PropertiesService.getUserProperties();
  var savedAdminId = props.getProperty(PROP_ADMIN_ID) || '';

  // Default NOTES to "Gmail Add-in" on first ever load
  var notesInitialized = props.getProperty(PROP_NOTES_INITIALIZED);
  var savedNotes;
  if (!notesInitialized) {
    savedNotes = 'Gmail Add-in';
    props.setProperty(PROP_NOTES, savedNotes);
    props.setProperty(PROP_NOTES_INITIALIZED, 'true');
  } else {
    savedNotes = props.getProperty(PROP_NOTES) || '';
  }

  var recipients = e.draftMetadata && e.draftMetadata.toRecipients
    ? e.draftMetadata.toRecipients
    : [];
  var defaultBackerId = recipients.length > 0 ? recipients[0] : '';

  var card = CardService.newCardBuilder()
    .setHeader(CardService.newCardHeader().setTitle('Pocket Fiche'))
    .addSection(
      CardService.newCardSection()
        .addWidget(
          CardService.newTextInput()
            .setFieldName('adminId')
            .setTitle('ADMIN-ID')
            .setValue(savedAdminId ? ADMIN_ID_MASK : '')
        )
        .addWidget(
          CardService.newTextInput()
            .setFieldName('backerId')
            .setTitle('BACKER-ID')
            .setValue(defaultBackerId)
        )
        .addWidget(
          CardService.newTextInput()
            .setFieldName('notes')
            .setTitle('NOTES')
            .setMultiline(true)
            .setValue(savedNotes)
        )
        .addWidget(
          CardService.newTextButton()
            .setText('Insert URL into Draft')
            .setComposeAction(
              CardService.newAction().setFunctionName('onInsertUrl'),
              CardService.ComposedEmailType.REPLY_AS_DRAFT
            )
        )
    )
    .build();

  return [card];
}

/**
 * Compose action callback — generates code and inserts URL into draft.
 */
function onInsertUrl(e) {
  var adminIdInput = (e.formInput.adminId || '').trim();
  var notes = (e.formInput.notes || '').trim();
  var backerId = (e.formInput.backerId || '').trim();

  // If user left the mask, use saved value; otherwise save the new one
  var props = PropertiesService.getUserProperties();
  var adminId;
  if (adminIdInput === ADMIN_ID_MASK) {
    adminId = props.getProperty(PROP_ADMIN_ID) || '';
  } else {
    adminId = adminIdInput;
    props.setProperty(PROP_ADMIN_ID, adminId);
  }
  props.setProperty(PROP_NOTES, notes);

  if (!adminId) {
    return notifyCompose('ADMIN-ID is required.');
  }
  if (!backerId) {
    return notifyCompose('BACKER-ID is required.');
  }

  var result = callGenerateCode(adminId, backerId, notes);
  if (result.error) {
    return notifyCompose(result.error);
  }

  var body = CardService.newUpdateDraftBodyAction()
    .addUpdateContent(result.url, CardService.ContentType.MUTABLE_HTML)
    .setUpdateType(CardService.UpdateDraftBodyType.IN_PLACE_INSERT);

  return CardService.newUpdateDraftActionResponseBuilder()
    .setUpdateDraftBodyAction(body)
    .build();
}

/**
 * Shared helper — calls the generate-code API.
 */
function callGenerateCode(adminId, backerId, notes) {
  var payload = {
    'command': 'generate-code',
    'admin-id': adminId,
    'backer-id': backerId,
    'notes': notes
  };

  var response;
  try {
    response = UrlFetchApp.fetch(API_URL, {
      method: 'post',
      payload: payload,
      muteHttpExceptions: true
    });
  } catch (err) {
    return { error: 'Network error: ' + err.message };
  }

  var json;
  try {
    json = JSON.parse(response.getContentText());
  } catch (err) {
    return { error: 'Invalid response from server.' };
  }

  if (json.status !== 'success') {
    return { error: json.message || 'Server returned an error.' };
  }

  return { url: UPLOAD_BASE_URL + '?code=' + json.code };
}

/**
 * Notification toast for compose actions.
 */
function notifyCompose(message) {
  return CardService.newActionResponseBuilder()
    .setNotification(CardService.newNotification().setText(message))
    .build();
}
