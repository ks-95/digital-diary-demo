import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

class ApiService {
  // Supply the HTTPS API address at build time for web, Android, and iOS:
  // flutter build web --dart-define=API_BASE_URL=https://api.example.com
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  static String? _token;
  static String? _userName;
  static String? _userStation;
  static String? _userMobile;

  static String? get userName => _userName;
  static String? get userStation => _userStation;
  static String? get userMobile => _userMobile;
  static bool get isLoggedIn => _token != null;

  static Map<String, String> _authHeaders({bool json = true}) {
    final headers = <String, String>{};
    if (json) headers['Content-Type'] = 'application/json';
    if (_token != null) headers['Authorization'] = 'Bearer $_token';
    return headers;
  }

  // ── AUTH ──────────────────────────────────────────────────────────────────
  static Future<dynamic> register({
    required String mobile,
    required String password,
    String? name,
    String? station,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/auth/register'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'mobile_number': mobile,
        'password': password,
        if (name != null && name.isNotEmpty) 'name': name,
        if (station != null && station.isNotEmpty) 'station': station,
      }),
    );
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 200 || response.statusCode == 201) {
      _token = data['access_token'];
      _userName = data['name'];
      _userStation = data['station'];
      _userMobile = data['mobile_number'];
      return data;
    }
    throw Exception(
        data['detail'] ?? 'Registration failed (${response.statusCode})');
  }

  static Future<dynamic> login({
    required String mobile,
    required String password,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'mobile_number': mobile, 'password': password}),
    );
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 200) {
      _token = data['access_token'];
      _userName = data['name'];
      _userStation = data['station'];
      _userMobile = data['mobile_number'];
      return data;
    }
    throw Exception(data['detail'] ?? 'Login failed (${response.statusCode})');
  }

  static void logout() {
    _token = null;
    _userName = null;
    _userStation = null;
    _userMobile = null;
  }

  // ── CASES ─────────────────────────────────────────────────────────────────
  static Future<List<dynamic>> fetchCases() async {
    final response = await http.get(
      Uri.parse('$baseUrl/cases/'),
      headers: _authHeaders(json: false),
    );
    if (response.statusCode == 200) return jsonDecode(response.body);
    throw Exception('Failed to load cases: ${response.statusCode}');
  }

  static Future<dynamic> createCase(Map<String, dynamic> caseData) async {
    final response = await http.post(
      Uri.parse('$baseUrl/cases/new_case'),
      headers: _authHeaders(),
      body: jsonEncode(caseData),
    );
    if (response.statusCode == 200 || response.statusCode == 201) {
      return jsonDecode(response.body);
    }
    throw Exception('Failed to create case: ${response.body}');
  }

  // ── EVIDENCE ─────────────────────────────────────────────────────────────
  static Future<List<dynamic>> fetchCaseEvidence(String caseId) async {
    final response = await http.get(
      Uri.parse('$baseUrl/cases/$caseId/evidence'),
      headers: _authHeaders(json: false),
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    }
    throw Exception('Failed to load evidence records');
  }

  static Future<List<dynamic>> fetchCaseFiles(String caseId) async {
    final response = await http.get(
      Uri.parse('$baseUrl/cases/$caseId/case-files'),
      headers: _authHeaders(json: false),
    );
    if (response.statusCode == 200) return jsonDecode(response.body);
    throw Exception('Failed to load case documents');
  }

  // ── DIARIES ───────────────────────────────────────────────────────────────
  static Future<List<dynamic>> fetchDiaries(String caseId) async {
    final response = await http.get(
      Uri.parse('$baseUrl/cases/$caseId/diaries/'),
      headers: _authHeaders(json: false),
    );
    if (response.statusCode == 200) return jsonDecode(response.body);
    throw Exception('Failed to load diary entries');
  }

  // ── Officer subscription ────────────────────────────────────────────────
  static Future<Map<String, dynamic>> fetchSubscriptionStatus() async {
    final response = await http.get(
      Uri.parse('$baseUrl/billing/me'),
      headers: _authHeaders(json: false),
    );
    final data = jsonDecode(response.body);
    if (response.statusCode == 200 && data is Map<String, dynamic>) {
      return data;
    }
    throw Exception(data is Map ? data['detail'] : 'Could not load subscription status');
  }

  static Future<Map<String, dynamic>> createSubscriptionCheckout() async {
    final response = await http.post(
      Uri.parse('$baseUrl/billing/subscribe'),
      headers: _authHeaders(json: false),
    );
    final data = jsonDecode(response.body);
    if ((response.statusCode == 200 || response.statusCode == 201) &&
        data is Map<String, dynamic>) {
      return data;
    }
    throw Exception(data is Map ? data['detail'] : 'Could not start subscription checkout');
  }

  static Future<dynamic> addDiaryEntry(
    String caseId,
    Map<String, dynamic> diaryData,
  ) async {
    final response = await http.post(
      Uri.parse('$baseUrl/cases/$caseId/diaries/'),
      headers: _authHeaders(),
      body: jsonEncode(diaryData),
    );
    if (response.statusCode == 201) return jsonDecode(response.body);
    throw Exception('Failed to add diary entry: ${response.body}');
  }

  // ── MoE (only valid when the case has a DSR number) ───────────────────────
  static Uri moeUri(String caseId, String dsrNumber) => Uri.parse(
      '$baseUrl/cases/$caseId/moe/download?dsr_number=${Uri.encodeQueryComponent(dsrNumber)}&token=${Uri.encodeQueryComponent(_token ?? '')}');

  static Uri exportDiaryUri(String caseId, {String format = 'docx'}) => Uri.parse(
      '$baseUrl/cases/$caseId/export-diary?format=$format&token=${Uri.encodeQueryComponent(_token ?? '')}');

  static Uri caseFileDownloadUri(String caseId, String fileId) => Uri.parse(
      '$baseUrl/cases/$caseId/case-files/$fileId/download?token=${Uri.encodeQueryComponent(_token ?? '')}');

  static Uri chargesheetUri(String caseId) => Uri.parse(
      '$baseUrl/cases/$caseId/chargesheet/generate?token=${Uri.encodeQueryComponent(_token ?? '')}');

  static Future<dynamic> uploadMoeFile(
      String caseId, String diaryId, Uint8List bytes, String fileName) async {
    final request = http.MultipartRequest('POST',
        Uri.parse('$baseUrl/cases/$caseId/diaries/$diaryId/moe-upload'));
    if (_token != null) request.headers['Authorization'] = 'Bearer $_token';
    request.files
        .add(http.MultipartFile.fromBytes('file', bytes, filename: fileName));
    final response = await http.Response.fromStream(await request.send());
    final body = jsonDecode(response.body);
    if (response.statusCode == 200) return body;
    throw Exception(
        body['detail'] ?? 'MoE upload failed (${response.statusCode})');
  }

  // ── CHARGESHEET ───────────────────────────────────────────────────────────
  static Future<Uint8List> downloadChargesheet(String caseId) async {
    final response = await http.post(
      Uri.parse('$baseUrl/cases/$caseId/chargesheet/generate'),
      headers: _authHeaders(json: false),
    );
    if (response.statusCode == 200) return response.bodyBytes;
    throw Exception('Chargesheet generation failed: ${response.body}');
  }

  // ── AI FIR SCAN ───────────────────────────────────────────────────────────
  static Future<dynamic> scanFirDocument(
    Uint8List imageBytes,
    String fileName,
  ) async {
    final uri = Uri.parse('$baseUrl/cases/scan-fir');
    final request = http.MultipartRequest('POST', uri);
    if (_token != null) request.headers['Authorization'] = 'Bearer $_token';
    request.files.add(http.MultipartFile.fromBytes(
      'file',
      imageBytes,
      filename: fileName.isNotEmpty ? fileName : 'fir_scan.jpg',
      contentType: MediaType.parse(_mimeOf(fileName)),
    ));
    final streamed = await request.send();
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode == 200) return jsonDecode(response.body);
    final err = jsonDecode(response.body);
    throw Exception(
        err['detail'] ?? 'FIR scan failed (${response.statusCode})');
  }

  static Future<dynamic> scanAndLodgeFirDocument(
    Uint8List imageBytes,
    String fileName,
  ) async {
    final uri = Uri.parse('$baseUrl/cases/scan-and-lodge');
    final request = http.MultipartRequest('POST', uri);
    if (_token != null) request.headers['Authorization'] = 'Bearer $_token';
    request.files.add(http.MultipartFile.fromBytes(
      'file',
      imageBytes,
      filename: fileName.isNotEmpty ? fileName : 'fir_scan.jpg',
      contentType: MediaType.parse(_mimeOf(fileName)),
    ));
    final streamed = await request.send();
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode == 200 || response.statusCode == 201) {
      return jsonDecode(response.body);
    }
    final err = jsonDecode(response.body);
    throw Exception(
        err['detail'] ?? 'Scan & lodge failed (${response.statusCode})');
  }

  static Future<dynamic> autoDiaryFromFir(
    String caseId,
    Uint8List imageBytes,
    String fileName,
  ) async {
    final uri = Uri.parse('$baseUrl/cases/$caseId/auto-diary-from-fir');
    final request = http.MultipartRequest('POST', uri);
    if (_token != null) request.headers['Authorization'] = 'Bearer $_token';
    request.files.add(http.MultipartFile.fromBytes(
      'file',
      imageBytes,
      filename: fileName.isNotEmpty ? fileName : 'scan.jpg',
      contentType: MediaType.parse(_mimeOf(fileName)),
    ));
    final streamed = await request.send();
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode == 200 || response.statusCode == 201) {
      return jsonDecode(response.body);
    }
    final err = jsonDecode(response.body);
    throw Exception(
        err['detail'] ?? 'Auto diary failed (${response.statusCode})');
  }

  static String _mimeOf(String name) {
    final lower = name.toLowerCase();
    if (lower.endsWith('.png')) return 'image/png';
    if (lower.endsWith('.webp')) return 'image/webp';
    if (lower.endsWith('.pdf')) return 'application/pdf';
    if (lower.endsWith('.doc')) return 'application/msword';
    if (lower.endsWith('.docx')) {
      return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
    }
    return 'image/jpeg';
  }
}
