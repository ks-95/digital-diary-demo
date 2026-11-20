import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/digital_diary_mark.dart';
import 'case_detail_screen.dart';
import 'login_screen.dart';

class CaseListScreen extends StatefulWidget {
  const CaseListScreen({super.key});
  @override
  State<CaseListScreen> createState() => _CaseListScreenState();
}

class _CaseListScreenState extends State<CaseListScreen> {
  late Future<List<dynamic>> _casesFuture;
  bool _scanning = false;

  @override
  void initState() {
    super.initState();
    _casesFuture = ApiService.fetchCases();
  }

  void _refreshCases() {
    setState(() {
      _casesFuture = ApiService.fetchCases();
    });
  }

  Future<void> _manageSubscription() async {
    try {
      final current = await ApiService.fetchSubscriptionStatus();
      if (current['active'] == true) {
        if (mounted) _snack('Officer subscription is active.');
        return;
      }
      final checkout = await ApiService.createSubscriptionCheckout();
      final checkoutUrl = Uri.tryParse(checkout['checkout_url']?.toString() ?? '');
      if (checkoutUrl == null || !checkoutUrl.hasScheme) {
        throw Exception('The payment provider returned an invalid checkout link.');
      }
      final opened = await launchUrl(checkoutUrl, mode: LaunchMode.externalApplication);
      if (!opened) throw Exception('Could not open the secure Razorpay checkout.');
      if (mounted) {
        _snack('Complete checkout, then return here and refresh your subscription status.');
      }
    } catch (e) {
      if (mounted) _snack('Subscription: $e', color: AppTheme.crimsonBadge);
    }
  }

  Future<PlatformFile?> _pickFirFile() async {
    final source = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: AppTheme.surfaceCard,
      builder: (ctx) => SafeArea(child: Wrap(children: [
        ListTile(leading: const Icon(Icons.camera_alt_outlined), title: const Text('Scan FIR with camera'), onTap: () => Navigator.pop(ctx, 'camera')),
        ListTile(leading: const Icon(Icons.folder_open_outlined), title: const Text('Choose PDF, Word, or image file'), onTap: () => Navigator.pop(ctx, 'file')),
      ])),
    );
    if (source == 'camera') {
      final photo = await ImagePicker().pickImage(source: ImageSource.camera, imageQuality: 90);
      if (photo == null) return null;
      final bytes = await photo.readAsBytes();
      return PlatformFile(name: photo.name, size: bytes.length, bytes: bytes);
    }
    if (source != 'file') return null;
    final result = await FilePicker.platform.pickFiles(type: FileType.custom,
        allowedExtensions: const ['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'webp', 'bmp', 'tif', 'tiff'], withData: true);
    return result?.files.isNotEmpty == true ? result!.files.single : null;
  }

  // ── 1-Click FIR Scan & Lodge ─────────────────────────────────────────────
  Future<void> _oneClickScanLodge() async {
    PlatformFile? image;
    try {
      image = await _pickFirFile();
    } catch (e) {
      if (mounted) _snack('File selection failed: $e', color: AppTheme.crimsonBadge);
      return;
    }
    if (image == null || !mounted) return;
    if (image.bytes == null || image.bytes!.isEmpty) {
      _snack('Could not read this file. Choose it again.', color: AppTheme.crimsonBadge);
      return;
    }

    setState(() {
      _scanning = true;
    });
    _snack('⚡ Scanning FIR with AI Vision…', duration: 60);
    try {
      final bytes = image.bytes!;
      final result =
          await ApiService.scanAndLodgeFirDocument(bytes, image.name);
      if (mounted) {
        ScaffoldMessenger.of(context).hideCurrentSnackBar();
        _snack(
          '✅ Case ${result['case']?['crime_number'] ?? ''} lodged + Day-1 Diary created!',
          color: AppTheme.greenVerified,
        );
        _refreshCases();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).hideCurrentSnackBar();
        _snack('❌ ${e.toString().replaceFirst("Exception: ", "")}',
            color: AppTheme.crimsonBadge);
      }
    } finally {
      if (mounted) {
        setState(() {
          _scanning = false;
        });
      }
    }
  }

  // ── Lodge Case Manually (with optional AI scan) ───────────────────────────
  void _showNewCaseDialog() {
    final crimeCtrl = TextEditingController();
    final firCtrl = TextEditingController();
    final dateCtrl = TextEditingController();
    final complainantCtrl = TextEditingController();
    final addrCtrl = TextEditingController();
    final phoneCtrl = TextEditingController();
    final sectionsCtrl = TextEditingController();
    final stolenCtrl = TextEditingController();
    final summaryCtrl = TextEditingController();

    Map<String, dynamic> lastArtifacts = {};
    String? lastDiarySummary;
    String? lastActionTaken;
    String investigationDomain = 'UNCLASSIFIED';
    bool isScanning = false;

    Future<void> doScan(StateSetter set) async {
      PlatformFile? image;
      try {
        image = await _pickFirFile();
      } catch (e) {
        if (mounted) _snack('File selection failed: $e', color: AppTheme.crimsonBadge);
        return;
      }
      if (image == null) return;
      if (image.bytes == null || image.bytes!.isEmpty) {
        _snack('Could not read this file. Choose it again.', color: AppTheme.crimsonBadge);
        return;
      }
      set(() {
        isScanning = true;
      });
      try {
        final bytes = image.bytes!;
        final data = await ApiService.scanFirDocument(bytes, image.name);
        set(() {
          isScanning = false;
          crimeCtrl.text = data['crime_number'] ?? '';
          firCtrl.text = data['fir_number'] ?? '';
          dateCtrl.text = data['complaint_date'] ?? '';
          complainantCtrl.text = data['complainant_name'] ?? '';
          addrCtrl.text = data['complainant_address'] ?? '';
          phoneCtrl.text = data['complainant_phone'] ?? '';
          stolenCtrl.text = data['stolen_property_value'] ?? '';
          summaryCtrl.text = data['complaint_summary'] ?? '';
          if (data['offense_sections'] is List) {
            sectionsCtrl.text = (data['offense_sections'] as List).join(', ');
          }
          if (data['tech_artifacts'] is Map) {
            lastArtifacts = Map<String, dynamic>.from(data['tech_artifacts']);
          }
          final diary = data['diary_entry'];
          investigationDomain = data['investigation_domain'] ?? 'UNCLASSIFIED';
          if (diary is Map) {
            lastDiarySummary = diary['investigation_summary'];
            lastActionTaken = diary['action_taken'];
          }
        });
      } catch (e) {
        set(() {
          isScanning = false;
        });
        if (mounted) {
          _snack('AI Scan Error: $e', color: AppTheme.crimsonBadge);
        }
      }
    }

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, set) => AlertDialog(
          backgroundColor: AppTheme.surfaceCard,
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Lodge New Case',
                  style: TextStyle(
                      color: AppTheme.textWhite, fontWeight: FontWeight.bold)),
              ElevatedButton.icon(
                onPressed: isScanning ? null : () => doScan(set),
                icon: isScanning
                    ? const SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.document_scanner, size: 16),
                label: Text(isScanning ? 'Scanning…' : '🔍 Scan FIR (AI)'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.tealAccent,
                  foregroundColor: AppTheme.navyDeep,
                  textStyle: const TextStyle(
                      fontSize: 12, fontWeight: FontWeight.bold),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10)),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                ),
              ),
            ],
          ),
          content: SizedBox(
            width: 500,
            child: SingleChildScrollView(
              child: Column(
                children: [
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: AppTheme.indigoPrime.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(
                          color: AppTheme.indigoPrime.withValues(alpha: 0.3)),
                    ),
                    child: const Text(
                      '💡 Tip: Click "Scan FIR (AI)" to auto-fill all fields from a photo of the FIR.',
                      style: TextStyle(fontSize: 12, color: AppTheme.textSoft),
                    ),
                  ),
                  const SizedBox(height: 14),
                  _dialogField(crimeCtrl, 'Crime No. (e.g., CY/2026/0142)'),
                  _dialogField(firCtrl, 'FIR Number'),
                  _dialogField(dateCtrl, 'Complaint Date (YYYY-MM-DD)',
                      keyboard: TextInputType.datetime),
                  _dialogField(complainantCtrl, 'Complainant Name'),
                  _dialogField(addrCtrl, 'Address'),
                  _dialogField(phoneCtrl, 'Phone Number',
                      keyboard: TextInputType.phone),
                  DropdownButtonFormField<String>(
                    initialValue: investigationDomain,
                    decoration: const InputDecoration(labelText: 'Case type'),
                    items: const [
                      DropdownMenuItem(value: 'UNCLASSIFIED', child: Text('Not classified')),
                      DropdownMenuItem(value: 'CYBER', child: Text('Cyber investigation')),
                      DropdownMenuItem(value: 'NON_CYBER', child: Text('Non-cyber investigation')),
                    ],
                    onChanged: (value) => set(() => investigationDomain = value ?? 'UNCLASSIFIED'),
                  ),
                  const SizedBox(height: 10),
                  _dialogField(sectionsCtrl, 'Offense Sections (comma-separated)'),
                  _dialogField(stolenCtrl, 'Stolen / Defrauded Amount'),
                  _dialogField(summaryCtrl, 'Case Summary', maxLines: 3),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel',
                  style: TextStyle(color: AppTheme.textSoft)),
            ),
            ElevatedButton(
              onPressed: () async {
                final sections = sectionsCtrl.text
                    .split(',')
                    .map((s) => s.trim())
                    .where((s) => s.isNotEmpty)
                    .toList();
                final payload = {
                  'crime_number': crimeCtrl.text.trim(),
                  'fir_number': firCtrl.text.trim(),
                  'complaint_date': dateCtrl.text.trim(),
                  'complainant_name': complainantCtrl.text.trim(),
                  'complainant_address': addrCtrl.text.trim(),
                  'complainant_phone': phoneCtrl.text.trim(),
                  'stolen_property_value': stolenCtrl.text.trim(),
                  'complaint_summary': summaryCtrl.text.trim(),
                  'offense_sections': sections,
                  'investigation_domain': investigationDomain,
                  'initial_diary_summary': lastDiarySummary,
                  'initial_action_taken': lastActionTaken,
                  'tech_artifacts': lastArtifacts,
                };
                try {
                  await ApiService.createCase(payload);
                  if (!mounted) return;
                  Navigator.of(context).pop();
                  _refreshCases();
                  _snack('✅ Case registered with Day-1 Diary!',
                      color: AppTheme.greenVerified);
                } catch (e) {
                  if (mounted) {
                    _snack('Error: $e', color: AppTheme.crimsonBadge);
                  }
                }
              },
              child: const Text('Save & Continue'),
            ),
          ],
        ),
      ),
    );
  }

  void _snack(String msg, {Color? color, int duration = 4}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg, style: const TextStyle(color: AppTheme.textWhite)),
        backgroundColor: color ?? AppTheme.surfaceElevated,
        duration: Duration(seconds: duration),
      ),
    );
  }

  static Widget _dialogField(
    TextEditingController ctrl,
    String label, {
    TextInputType keyboard = TextInputType.text,
    int maxLines = 1,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: TextField(
        controller: ctrl,
        keyboardType: keyboard,
        maxLines: maxLines,
        style: const TextStyle(color: AppTheme.textWhite, fontSize: 13),
        decoration: InputDecoration(
          labelText: label,
          labelStyle: const TextStyle(fontSize: 12, color: AppTheme.textSoft),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final isWide = size.width > 800;

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(gradient: AppTheme.bgGradient),
        child: Column(
          children: [
            _buildAppBar(isWide),
            Expanded(
              child: FutureBuilder<List<dynamic>>(
                future: _casesFuture,
                builder: (ctx, snap) {
                  if (snap.connectionState == ConnectionState.waiting) {
                    return const Center(
                      child:
                          CircularProgressIndicator(color: AppTheme.tealAccent),
                    );
                  }
                  if (snap.hasError) {
                    return _errorView(snap.error.toString());
                  }
                  final cases = snap.data ?? [];
                  if (cases.isEmpty) return _emptyView();

                  final isGrid = isWide && cases.length > 1;
                  if (isGrid) {
                    return GridView.builder(
                      padding: const EdgeInsets.all(16),
                      gridDelegate:
                          const SliverGridDelegateWithMaxCrossAxisExtent(
                        maxCrossAxisExtent: 400,
                        mainAxisSpacing: 12,
                        crossAxisSpacing: 12,
                        childAspectRatio: 2.2,
                      ),
                      itemCount: cases.length,
                      itemBuilder: (_, i) => _caseCard(cases[i]),
                    );
                  }
                  return ListView.builder(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    itemCount: cases.length,
                    itemBuilder: (_, i) => _caseCard(cases[i]),
                  );
                },
              ),
            ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _showNewCaseDialog,
        icon: const Icon(Icons.add, color: AppTheme.navyDeep),
        label: const Text(
          'Lodge Case',
          style:
              TextStyle(color: AppTheme.navyDeep, fontWeight: FontWeight.bold),
        ),
        backgroundColor: AppTheme.goldAccent,
        elevation: 8,
      ),
    );
  }

  Widget _buildAppBar(bool isWide) {
    return Container(
      padding: EdgeInsets.only(
        top: MediaQuery.of(context).padding.top + 8,
        left: 16,
        right: 8,
        bottom: 12,
      ),
      decoration: const BoxDecoration(
        color: AppTheme.surfaceCard,
        boxShadow: [BoxShadow(color: Colors.black38, blurRadius: 10)],
      ),
      child: Row(
        children: [
          const DigitalDiaryMark(size: 40),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'DIGITAL DIARY',
                  style: TextStyle(
                    color: AppTheme.goldAccent,
                    fontSize: 16,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 2,
                  ),
                ),
                if (ApiService.userStation != null)
                  Text(
                    ApiService.userStation!,
                    style:
                        const TextStyle(color: AppTheme.textSoft, fontSize: 10),
                    overflow: TextOverflow.ellipsis,
                  ),
              ],
            ),
          ),
          _scanning
              ? const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 12),
                  child: SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: AppTheme.goldAccent),
                  ),
                )
              : TextButton.icon(
                  onPressed: _oneClickScanLodge,
                  icon: const Icon(Icons.flash_on,
                      color: AppTheme.goldAccent, size: 18),
                  label: const Text(
                    '1-Click FIR',
                    style: TextStyle(
                      color: AppTheme.goldAccent,
                      fontWeight: FontWeight.bold,
                      fontSize: 13,
                    ),
                  ),
                ),
          IconButton(
            icon: const Icon(Icons.workspace_premium_outlined,
                color: AppTheme.goldAccent),
            tooltip: 'Officer subscription',
            onPressed: _manageSubscription,
          ),
          IconButton(
            icon: const Icon(Icons.refresh, color: AppTheme.textSoft),
            onPressed: _refreshCases,
            tooltip: 'Refresh',
          ),
          IconButton(
            icon: const Icon(Icons.logout, color: AppTheme.crimsonBadge),
            tooltip: 'Logout',
            onPressed: () {
              ApiService.logout();
              Navigator.pushAndRemoveUntil(
                context,
                MaterialPageRoute(builder: (_) => const LoginScreen()),
                (route) => false,
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _caseCard(Map<String, dynamic> item) {
    final sections = item['offense_sections'];
    final sectionText =
        sections is List ? sections.take(2).join(', ') : (sections ?? '');

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 6, horizontal: 2),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => CaseDetailScreen(caseData: item)),
        ).then((_) => _refreshCases()),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              Container(
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  gradient: AppTheme.primaryGradient,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(Icons.folder_special,
                    color: Colors.white, size: 24),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${item['crime_number'] ?? 'N/A'}',
                      style: const TextStyle(
                        color: AppTheme.textWhite,
                        fontWeight: FontWeight.bold,
                        fontSize: 14,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'FIR: ${item['fir_number'] ?? 'N/A'} • ${item['complainant_name'] ?? ''}',
                      style: const TextStyle(
                          color: AppTheme.textSoft, fontSize: 12),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 4),
                    if (sectionText.isNotEmpty)
                      Text(
                        sectionText,
                        style: const TextStyle(
                            color: AppTheme.tealAccent, fontSize: 11),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: AppTheme.greenVerified.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                      color: AppTheme.greenVerified.withValues(alpha: 0.4)),
                ),
                child: Text(
                  item['case_status'] ?? 'ACTIVE',
                  style: const TextStyle(
                    color: AppTheme.greenVerified,
                    fontSize: 10,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              const Icon(Icons.arrow_forward_ios,
                  size: 14, color: AppTheme.textSoft),
            ],
          ),
        ),
      ),
    );
  }

  Widget _emptyView() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 90,
            height: 90,
            decoration: BoxDecoration(
              gradient: AppTheme.primaryGradient,
              borderRadius: BorderRadius.circular(22),
            ),
            child: const Icon(Icons.folder_open, size: 50, color: Colors.white),
          ),
          const SizedBox(height: 20),
          const Text(
            'No Active Cases',
            style: TextStyle(
                color: AppTheme.textWhite,
                fontSize: 20,
                fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          const Text(
            'Lodge a new case or scan a FIR to get started.',
            style: TextStyle(color: AppTheme.textSoft, fontSize: 13),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 28),
          ElevatedButton.icon(
            onPressed: _showNewCaseDialog,
            icon: const Icon(Icons.add),
            label: const Text('Lodge New Case'),
          ),
        ],
      ),
    );
  }

  Widget _errorView(String err) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.wifi_off, size: 60, color: AppTheme.crimsonBadge),
            const SizedBox(height: 16),
            const Text(
              'Cannot connect to server',
              style: TextStyle(
                  color: AppTheme.textWhite,
                  fontSize: 18,
                  fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            const Text(
              'Make sure FastAPI is running on http://127.0.0.1:8000',
              style: TextStyle(color: AppTheme.textSoft, fontSize: 12),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
            ElevatedButton.icon(
              onPressed: _refreshCases,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}
