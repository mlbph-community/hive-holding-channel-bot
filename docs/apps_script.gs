const DEFAULT_TAB = 'Weekly Schedule';

function setApiSecret() {
  PropertiesService.getScriptProperties().setProperty(
    'API_SECRET',
    'replace-this-with-a-long-random-secret'
  );
}

function doGet(e) {
  const params = (e && e.parameter) || {};
  return route_(params);
}

function doPost(e) {
  const body = e && e.postData && e.postData.contents
    ? JSON.parse(e.postData.contents)
    : {};
  return route_(body);
}

function route_(params) {
  try {
    const secret = PropertiesService.getScriptProperties().getProperty('API_SECRET');
    if (!secret) return json_({ ok: false, error: 'API_SECRET is not set' });
    if ((params.secret || '') !== secret) {
      return json_({ ok: false, error: 'Unauthorized' });
    }

    const action = String(params.action || 'list_posts');
    const tabName = String(params.tab || DEFAULT_TAB);

    switch (action) {
      case 'health':
        return json_({
          ok: true,
          spreadsheet: SpreadsheetApp.getActiveSpreadsheet().getName(),
          tab: tabName,
        });

      case 'list_posts':
        return json_({ ok: true, posts: listRows_(tabName) });

      case 'update_status':
        updateCellByHeader_(tabName, Number(params.row_number), 'Status', String(params.status || ''));
        return json_({ ok: true });

      case 'update_note':
        updateCellByHeader_(tabName, Number(params.row_number), 'Notes', String(params.note || ''));
        return json_({ ok: true });

      default:
        return json_({ ok: false, error: 'Unsupported action: ' + action });
    }
  } catch (err) {
    return json_({ ok: false, error: String(err && err.message ? err.message : err) });
  }
}

function listRows_(tabName) {
  const sheet = getSheet_(tabName);
  const values = sheet.getDataRange().getDisplayValues();
  if (!values.length) return [];

  const headers = values[0].map(String);
  const rows = values.slice(1).filter(row => row.some(cell => String(cell).trim() !== ''));

  return rows.map(row => {
    const obj = {};
    headers.forEach((header, i) => {
      obj[header] = row[i] || '';
    });
    return obj;
  });
}

function updateCellByHeader_(tabName, rowNumber, headerName, value) {
  if (!rowNumber || rowNumber < 2) {
    throw new Error('Invalid row number: ' + rowNumber);
  }

  const sheet = getSheet_(tabName);
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
  const colIndex = headers.indexOf(headerName) + 1;
  if (!colIndex) {
    throw new Error('Missing required header: ' + headerName);
  }

  sheet.getRange(rowNumber, colIndex).setValue(value);
}

function getSheet_(tabName) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(tabName);
  if (!sheet) {
    throw new Error('Tab not found: ' + tabName);
  }
  return sheet;
}

function json_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
