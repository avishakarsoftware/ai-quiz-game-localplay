<?php
// LocalPlay IONOS media upload handler.
// Deploy under https://media.revelryapp.me/apps/localplay/upload.php.

$allowedOrigins = [
    'https://games.revelryapp.me',
    'https://gamesapi.revelryapp.me',
    'https://gamesapi-gamma.revelryapp.me',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
];

$origin = $_SERVER['HTTP_ORIGIN'] ?? '';
if (in_array($origin, $allowedOrigins, true)) {
    header("Access-Control-Allow-Origin: $origin");
    header('Vary: Origin');
}
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

function fail($status, $message) {
    http_response_code($status);
    echo json_encode(['error' => $message]);
    exit;
}

function read_upload_secret() {
    $phpSecretPath = __DIR__ . '/upload-secret.php';
    if (is_file($phpSecretPath)) {
        $secret = require $phpSecretPath;
        $secret = is_string($secret) ? trim($secret) : '';
        if ($secret !== '') {
            return $secret;
        }
    }

    // Legacy fallback. Prefer upload-secret.php because plain dotfiles may be
    // served by some shared-host docroots.
    $legacySecretPath = __DIR__ . '/.upload_secret';
    if (is_file($legacySecretPath)) {
        return trim(file_get_contents($legacySecretPath));
    }

    return '';
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    fail(405, 'method_not_allowed');
}

$secret = read_upload_secret();
if ($secret === '') {
    fail(500, 'upload_secret_missing');
}

$path = $_POST['path'] ?? '';
$expires = intval($_POST['expires'] ?? '0');
$mimeType = $_POST['mime_type'] ?? '';
$bytes = intval($_POST['bytes'] ?? '0');
$token = $_POST['token'] ?? '';
$filename = $_FILES['file']['name'] ?? '';
$dangerousExtensions = [
    'asa', 'asax', 'ascx', 'ashx', 'asp', 'aspx', 'bat', 'cgi', 'cmd',
    'config', 'exe', 'htaccess', 'html', 'js', 'jsp', 'jspx', 'php',
    'php3', 'php4', 'php5', 'php7', 'phtml', 'phar', 'pl', 'py', 'shtml',
    'sh', 'svg',
];

if ($path === '' || $expires <= time() || $mimeType === '' || $bytes <= 0 || $token === '') {
    fail(400, 'invalid_fields');
}
if ($filename !== '') {
    foreach (explode('.', strtolower($filename)) as $extensionPart) {
        if (in_array($extensionPart, $dangerousExtensions, true)) {
            fail(415, 'dangerous_extension');
        }
    }
}
if (!preg_match('/^(local|gamma|prod)\/uploads\/[A-Za-z0-9_-]+\/\d{4}\/\d{2}\/\d{2}\/img_[a-f0-9]+\.(png|jpg|webp)$/', $path)) {
    fail(400, 'invalid_path');
}
if (!in_array($mimeType, ['image/png', 'image/jpeg', 'image/webp'], true)) {
    fail(400, 'invalid_mime_type');
}
if ($bytes > 2 * 1024 * 1024) {
    fail(413, 'file_too_large');
}

$payload = $path . "\n" . $expires . "\n" . $mimeType . "\n" . $bytes;
$expected = hash_hmac('sha256', $payload, $secret);
if (!hash_equals($expected, $token)) {
    fail(403, 'bad_signature');
}
if (!isset($_FILES['file']) || $_FILES['file']['error'] !== UPLOAD_ERR_OK) {
    fail(400, 'upload_failed');
}
if ($_FILES['file']['size'] !== $bytes || $_FILES['file']['size'] > 2 * 1024 * 1024) {
    fail(413, 'size_mismatch');
}

$finfo = new finfo(FILEINFO_MIME_TYPE);
$actualMime = $finfo->file($_FILES['file']['tmp_name']);
if ($actualMime !== $mimeType) {
    fail(400, 'mime_mismatch');
}

$root = realpath(__DIR__);
$target = $root . '/' . $path;
$targetDir = dirname($target);
if (!is_dir($targetDir) && !mkdir($targetDir, 0755, true)) {
    fail(500, 'mkdir_failed');
}
$resolvedTargetDir = realpath($targetDir);
if ($resolvedTargetDir === false || strpos($resolvedTargetDir . DIRECTORY_SEPARATOR, $root . DIRECTORY_SEPARATOR) !== 0) {
    fail(400, 'path_escape');
}
if (!move_uploaded_file($_FILES['file']['tmp_name'], $target)) {
    fail(500, 'move_failed');
}
chmod($target, 0644);

echo json_encode([
    'ok' => true,
    'path' => $path,
    'bytes' => $bytes,
    'mime_type' => $mimeType,
]);
