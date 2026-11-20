import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:file_picker/file_picker.dart';
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

class CaseDetailScreen extends StatefulWidget {
  final Map<String, dynamic> caseData;
  const CaseDetailScreen({super.key, required this.caseData});
  @override
  State<CaseDetailScreen> createState() => _CaseDetailScreenState();
}

class _CaseDetailScreenState extends State<CaseDetailScreen> {
  late Future<List<dynamic>> _diariesFuture;
  late Future<List<dynamic>> _evidenceFuture;
  late Future<List<dynamic>> _caseFilesFuture;
  bool _generatingChargesheet = false;

  @override
  void initState() {
    super.initState();
    _refreshData();
  }

  void _refreshData() {
    setState(() {
      _diariesFuture = ApiService.fetchDiaries(caseId);
      _evidenceFuture = ApiService.fetchCaseEvidence(caseId);
      _caseFilesFuture = ApiService.fetchCaseFiles(caseId);
    });
  }

  String get caseId => widget.caseData['case_id'] ?? '';

  Future<List<PlatformFile>> _pickCaseDocuments() async {
    final source = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: AppTheme.surfaceCard,
      builder: (ctx) => SafeArea(child: Wrap(children: [
        ListTile(leading: const Icon(Icons.camera_alt_outlined), title: const Text('Scan with camera'), onTap: () => Navigator.pop(ctx, 'camera')),
        ListTile(leading: const Icon(Icons.folder_open_outlined), title: const Text('Choose up to 50 PDF, Word, or image files'), onTap: () => Navigator.pop(ctx, 'file')),
      ])),
    );
    if (source == 'camera') {
      final photo = await ImagePicker().pickImage(source: ImageSource.camera, imageQuality: 90);
      if (photo == null) return [];
      final bytes = await photo.readAsBytes();
      return [PlatformFile(name: photo.name, size: bytes.length, bytes: bytes)];
    }
    if (source != 'file') return [];
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'webp', 'bmp', 'tif', 'tiff'],
      allowMultiple: true,
      withData: true,
    );
    final files = result?.files ?? <PlatformFile>[];
    if (files.length > 50 && mounted) {
      _snack('Select up to 50 files per upload.', color: AppTheme.crimsonBadge);
      return [];
    }
    return files;
  }

  // ── Chargesheet ──────────────────────────────────────────────────────────
  Future<void> _generateChargesheet() async {
    setState(() {
      _generatingChargesheet = true;
    });
    _snack('⚙️ Generating AI Chargesheet under Sec 193 BNSS…', duration: 60);
    try {
      await launchUrl(ApiService.chargesheetUri(caseId),
          mode: LaunchMode.externalApplication);
      if (mounted) {
        ScaffoldMessenger.of(context).hideCurrentSnackBar();
        _snack('✅ Chargesheet opened/downloaded.',
            color: AppTheme.greenVerified);
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
          _generatingChargesheet = false;
        });
      }
    }
  }

  Future<void> _askDsrAndOpenMoE() async {
    final ctrl = TextEditingController();
    final dsr = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppTheme.surfaceCard,
        title: const Text('Memo of Evidence',
            style: TextStyle(color: AppTheme.textWhite)),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          style: const TextStyle(color: AppTheme.textWhite),
          decoration:
              const InputDecoration(labelText: 'DSR Number (e.g., 43/25)'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          ElevatedButton(
              onPressed: () => Navigator.pop(ctx, ctrl.text.trim()),
              child: const Text('Generate MoE')),
        ],
      ),
    );
    if (dsr == null) return;
    if (dsr.isEmpty) {
      _snack('MoE needs a DSR number.', color: AppTheme.crimsonBadge);
      return;
    }
    await launchUrl(ApiService.moeUri(caseId, dsr),
        mode: LaunchMode.externalApplication);
  }

  // ── Scan document / Seizure list → new diary & evidence entry ─────────────
  Future<void> _scanToDiary() async {
    List<PlatformFile> selected;
    try {
      selected = await _pickCaseDocuments();
    } catch (e) {
      if (mounted) _snack('File selection failed: $e', color: AppTheme.crimsonBadge);
      return;
    }
    if (selected.isEmpty || !mounted) return;
    var completed = 0;
    final failures = <String>[];
    for (final file in selected) {
      final bytes = file.bytes;
      if (bytes == null || bytes.isEmpty) {
        failures.add('${file.name}: unreadable');
        continue;
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).hideCurrentSnackBar();
      _snack('Scanning ${completed + failures.length + 1}/${selected.length}: ${file.name}', duration: 60);
      try {
        await ApiService.autoDiaryFromFir(caseId, bytes, file.name);
        completed++;
      } catch (e) {
        failures.add('${file.name}: ${e.toString().replaceFirst("Exception: ", "")}');
      }
    }
    if (!mounted) return;
    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    _refreshData();
    _snack(failures.isEmpty
        ? 'Scanned and saved $completed file(s). Review extracted details before using them in official records.'
        : 'Saved $completed file(s); ${failures.length} failed. ${failures.take(2).join("; ")}',
      color: failures.isEmpty ? AppTheme.greenVerified : AppTheme.crimsonBadge,
      duration: 12);
  }

  // ── Add Diary Manually (with MoE option) ─────────────────────────────────
  void _showAddDiaryDialog() {
    final summaryCtrl = TextEditingController();
    final actionCtrl = TextEditingController();
    final dsrCtrl = TextEditingController();
    final nowTime = TimeOfDay.now();
    final diaryTimeCtrl = TextEditingController(
        text: '${nowTime.hour.toString().padLeft(2, '0')}:${nowTime.minute.toString().padLeft(2, '0')}');
    bool showMoE = false;
    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, set) => AlertDialog(
          backgroundColor: AppTheme.surfaceCard,
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: const Text(
            'Add Case Diary Entry',
            style: TextStyle(
                color: AppTheme.textWhite, fontWeight: FontWeight.bold),
          ),
          content: SizedBox(
            width: 480,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    controller: diaryTimeCtrl,
                    style: const TextStyle(color: AppTheme.textWhite, fontSize: 13),
                    decoration: const InputDecoration(labelText: 'Diary entry time (local)', hintText: 'e.g., 14:35'),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: summaryCtrl,
                    maxLines: 4,
                    style: const TextStyle(
                        color: AppTheme.textWhite, fontSize: 13),
                    decoration: const InputDecoration(
                      labelText: 'Investigation Summary',
                      hintText:
                          'e.g., Examined bank records, issued notice to TSP…',
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: actionCtrl,
                    maxLines: 3,
                    style: const TextStyle(
                        color: AppTheme.textWhite, fontSize: 13),
                    decoration: const InputDecoration(
                      labelText: 'Action Taken',
                      hintText: 'e.g., Freeze order sent to Axis Bank.',
                    ),
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: dsrCtrl,
                          style: const TextStyle(
                              color: AppTheme.textWhite, fontSize: 13),
                          onChanged: (v) {
                            set(() {
                              showMoE = v.trim().isNotEmpty;
                            });
                          },
                          decoration: const InputDecoration(
                            labelText: 'DSR Number (optional)',
                            hintText: 'e.g., DSR/2026/001',
                            prefixIcon: Icon(Icons.numbers,
                                color: AppTheme.goldAccent, size: 18),
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      AnimatedSwitcher(
                        duration: const Duration(milliseconds: 300),
                        child: showMoE
                            ? Tooltip(
                                message: 'Attach Memo of Evidence (MoE)',
                                child: InkWell(
                                  onTap: () async {
                                    final ok = await launchUrl(
                                      ApiService.moeUri(
                                          caseId, dsrCtrl.text.trim()),
                                      mode: LaunchMode.externalApplication,
                                    );
                                    if (!ok && ctx.mounted) {
                                      _snack('Could not open MoE document.',
                                          color: AppTheme.crimsonBadge);
                                    }
                                  },
                                  borderRadius: BorderRadius.circular(12),
                                  child: Container(
                                    padding: const EdgeInsets.all(10),
                                    decoration: BoxDecoration(
                                      gradient: AppTheme.goldGradient,
                                      borderRadius: BorderRadius.circular(12),
                                      boxShadow: [
                                        BoxShadow(
                                          color: AppTheme.goldAccent
                                              .withValues(alpha: 0.4),
                                          blurRadius: 12,
                                        ),
                                      ],
                                    ),
                                    child: const Column(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        Icon(Icons.description_outlined,
                                            color: AppTheme.navyDeep, size: 22),
                                        SizedBox(height: 2),
                                        Text(
                                          'MoE',
                                          style: TextStyle(
                                            color: AppTheme.navyDeep,
                                            fontSize: 10,
                                            fontWeight: FontWeight.bold,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              )
                            : const SizedBox(
                                key: ValueKey('empty'), width: 52, height: 52),
                      ),
                    ],
                  ),
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
            ElevatedButton.icon(
              onPressed: () async {
                if (summaryCtrl.text.trim().isEmpty ||
                    actionCtrl.text.trim().isEmpty) {
                  _snack('Investigation Summary and Action Taken are required.',
                      color: AppTheme.crimsonBadge);
                  return;
                }

                final payload = {
                  'investigation_summary': summaryCtrl.text.trim(),
                  'action_taken': actionCtrl.text.trim(),
                  'diary_entry_time': diaryTimeCtrl.text.trim(),
                  'tech_artifacts_obtained': {},
                  if (dsrCtrl.text.trim().isNotEmpty)
                    'dsr_number': dsrCtrl.text.trim(),
                };
                try {
                  await ApiService.addDiaryEntry(caseId, payload);

                  if (!mounted) return;
                  Navigator.of(context).pop();

                  _refreshData();
                  _snack('✅ Diary entry saved!', color: AppTheme.greenVerified);
                } catch (e) {
                  if (mounted) {
                    _snack('Error: $e', color: AppTheme.crimsonBadge);
                  }
                }
              },
              icon: const Icon(Icons.save_outlined, size: 16),
              label: const Text('Save Entry'),
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

  @override
  Widget build(BuildContext context) {
    final caseData = widget.caseData;
    final sections = caseData['offense_sections'];
    final sectionStr =
        sections is List ? sections.join(', ') : (sections ?? '');

    return DefaultTabController(
      length: 3,
      child: Scaffold(
        body: Container(
          decoration: const BoxDecoration(gradient: AppTheme.bgGradient),
          child: Column(
            children: [
              _buildAppBar(caseData),
              Container(
                width: double.infinity,
                margin: const EdgeInsets.fromLTRB(12, 10, 12, 0),
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [Color(0xFF1A237E), Color(0xFF283593)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(16),
                  border:
                      Border.all(color: AppTheme.indigoPrime.withValues(alpha: 0.5)),
                  boxShadow: [
                    BoxShadow(
                      color: AppTheme.indigoPrime.withValues(alpha: 0.4),
                      blurRadius: 20,
                    ),
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.folder_special,
                            color: AppTheme.goldAccent, size: 20),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            caseData['crime_number'] ?? 'N/A',
                            style: const TextStyle(
                              color: AppTheme.goldAccent,
                              fontWeight: FontWeight.w900,
                              fontSize: 18,
                              letterSpacing: 1,
                            ),
                          ),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            color: AppTheme.greenVerified.withValues(alpha: 0.2),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(
                                color: AppTheme.greenVerified.withValues(alpha: 0.5)),
                          ),
                          child: Text(
                            caseData['case_status'] ?? 'ACTIVE',
                            style: const TextStyle(
                              color: AppTheme.greenVerified,
                              fontSize: 11,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    _infoRow(Icons.confirmation_number_outlined, 'FIR No',
                        caseData['fir_number']),
                    _infoRow(Icons.category_outlined, 'Investigation Type',
                        caseData['investigation_domain'] == 'CYBER'
                            ? 'Cyber'
                            : caseData['investigation_domain'] == 'NON_CYBER'
                                ? 'Non-cyber'
                                : 'Unclassified'),
                    _infoRow(Icons.local_police_outlined, 'Police Station',
                        caseData['police_station']),
                    _infoRow(Icons.person_outline, 'Complainant',
                        caseData['complainant_name']),
                    if (caseData['complainant_phone'] != null)
                      _infoRow(Icons.phone_outlined, 'Phone',
                          caseData['complainant_phone']),
                    if (caseData['complainant_address'] != null &&
                        caseData['complainant_address'].toString().isNotEmpty)
                      _infoRow(Icons.location_on_outlined, 'Address',
                          caseData['complainant_address']),
                    if (sectionStr.isNotEmpty)
                      _infoRow(Icons.gavel_outlined, 'Sections', sectionStr),
                    if (caseData['stolen_property_value'] != null &&
                        caseData['stolen_property_value'].toString().isNotEmpty)
                      _infoRow(Icons.currency_rupee, 'Amount',
                          caseData['stolen_property_value'],
                          valueColor: AppTheme.crimsonBadge),
                  ],
                ),
              ),
              const SizedBox(height: 10),
              // ── TabBar for Case Diaries & Seized Evidence ──────────────
              const TabBar(
                isScrollable: true,
                labelColor: AppTheme.goldAccent,
                unselectedLabelColor: AppTheme.textSoft,
                indicatorColor: AppTheme.goldAccent,
                tabs: [
                  Tab(
                      icon: Icon(Icons.book_outlined, size: 18),
                      text: 'Case Diaries'),
                  Tab(
                      icon: Icon(Icons.inventory_2_outlined, size: 18),
                      text: 'Seized Evidence'),
                  Tab(
                      icon: Icon(Icons.folder_copy_outlined, size: 18),
                      text: 'Case Documents'),
                ],
              ),
              // ── TabBarView ─────────────────────────────────────────────
              Expanded(
                child: TabBarView(
                  children: [
                    _buildDiaryListView(),
                    _buildEvidenceListView(),
                    _buildCaseFilesListView(),
                  ],
                ),
              ),
            ],
          ),
        ),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: _showAddDiaryDialog,
          icon: const Icon(Icons.edit_note, color: AppTheme.navyDeep),
          label: const Text(
            'Add Diary',
            style: TextStyle(
                color: AppTheme.navyDeep, fontWeight: FontWeight.bold),
          ),
          backgroundColor: AppTheme.goldAccent,
        ),
      ),
    );
  }

  Widget _buildDiaryListView() {
    return FutureBuilder<List<dynamic>>(
      future: _diariesFuture,
      builder: (ctx, snap) {
        if (snap.connectionState == ConnectionState.waiting) {
          return const Center(
              child: CircularProgressIndicator(color: AppTheme.tealAccent));
        }
        if (snap.hasError) {
          return Center(
            child: Text('Error: ${snap.error}',
                style: const TextStyle(color: AppTheme.crimsonBadge)),
          );
        }
        final entries = snap.data ?? [];
        if (entries.isEmpty) {
          return Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.book_outlined,
                    size: 48, color: AppTheme.textSoft),
                const SizedBox(height: 12),
                const Text('No diary entries yet.',
                    style: TextStyle(color: AppTheme.textSoft)),
                const SizedBox(height: 16),
                ElevatedButton.icon(
                  onPressed: _showAddDiaryDialog,
                  icon: const Icon(Icons.edit_note),
                  label: const Text('Add First Entry'),
                ),
              ],
            ),
          );
        }
        return ListView.builder(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 100),
          itemCount: entries.length,
          itemBuilder: (_, i) => _diaryCard(entries[i], i + 1),
        );
      },
    );
  }

  Widget _buildEvidenceListView() {
    return FutureBuilder<List<dynamic>>(
      future: _evidenceFuture,
      builder: (ctx, snap) {
        if (snap.connectionState == ConnectionState.waiting) {
          return const Center(
              child: CircularProgressIndicator(color: AppTheme.tealAccent));
        }
        if (snap.hasError) {
          return Center(
            child: Text('Error: ${snap.error}',
                style: const TextStyle(color: AppTheme.crimsonBadge)),
          );
        }
        final items = snap.data ?? [];
        if (items.isEmpty) {
          return Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.inventory_2_outlined,
                    size: 48, color: AppTheme.textSoft),
                const SizedBox(height: 12),
                const Text('No evidence records uploaded yet.',
                    style: TextStyle(color: AppTheme.textSoft)),
                const SizedBox(height: 16),
                ElevatedButton.icon(
                  onPressed: _scanToDiary,
                  icon: const Icon(Icons.document_scanner),
                  label: const Text('Add Evidence / Case Record'),
                ),
              ],
            ),
          );
        }
        return ListView.builder(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 100),
          itemCount: items.length,
          itemBuilder: (_, i) {
            final item = items[i];
            return Card(
              color: AppTheme.surfaceCard,
              margin: const EdgeInsets.only(bottom: 12),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side: BorderSide(color: AppTheme.indigoPrime.withValues(alpha: 0.4)),
              ),
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Row(
                  children: [
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        gradient: AppTheme.goldGradient,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Icon(Icons.folder_shared,
                          color: AppTheme.navyDeep, size: 22),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            item['title'] ?? item['artifact_type'] ?? 'EVIDENCE',
                            style: const TextStyle(
                              color: AppTheme.goldAccent,
                              fontWeight: FontWeight.bold,
                              fontSize: 14,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            item['original_filename'] ?? item['artifact_type'] ?? 'Stored case file',
                            style: const TextStyle(
                                color: AppTheme.textSoft, fontSize: 11),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          const SizedBox(height: 2),
                          Text(
                            'Uploaded: ${item['uploaded_at']}',
                            style: const TextStyle(
                                color: AppTheme.textSoft, fontSize: 10),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      tooltip: 'Open original file',
                      icon: const Icon(Icons.open_in_new, color: AppTheme.tealAccent),
                      onPressed: () => launchUrl(
                        ApiService.caseFileDownloadUri(caseId, item['evidence_id']),
                        mode: LaunchMode.externalApplication,
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  Widget _buildCaseFilesListView() {
    return FutureBuilder<List<dynamic>>(
      future: _caseFilesFuture,
      builder: (ctx, snap) {
        if (snap.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator(color: AppTheme.tealAccent));
        }
        if (snap.hasError) {
          return Center(child: Text('Could not load case documents: ${snap.error}', style: const TextStyle(color: AppTheme.crimsonBadge)));
        }
        final items = snap.data ?? [];
        return Column(children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: SizedBox(width: double.infinity, child: OutlinedButton.icon(
              onPressed: _scanToDiary,
              icon: const Icon(Icons.document_scanner_outlined),
              label: const Text('Scan / Add Case Document'),
            )),
          ),
          Expanded(child: items.isEmpty
              ? const Center(child: Text('Court papers, CC certificates, seizure lists, CMR receipts, and other case documents will appear here.', textAlign: TextAlign.center, style: TextStyle(color: AppTheme.textSoft)))
              : ListView.builder(
                  padding: const EdgeInsets.fromLTRB(12, 0, 12, 100),
                  itemCount: items.length,
                  itemBuilder: (_, i) {
                    final item = items[i];
                    return Card(child: ListTile(
                      leading: const Icon(Icons.description_outlined, color: AppTheme.tealAccent),
                      title: Text(item['title'] ?? item['artifact_type'] ?? 'Case document'),
                      subtitle: Text('${item['artifact_type'] ?? 'DOCUMENT'} • ${item['uploaded_at'] ?? ''}', maxLines: 2, overflow: TextOverflow.ellipsis),
                      trailing: IconButton(
                        tooltip: 'Open original file',
                        icon: const Icon(Icons.open_in_new, color: AppTheme.tealAccent),
                        onPressed: () => launchUrl(
                          ApiService.caseFileDownloadUri(caseId, item['evidence_id']),
                          mode: LaunchMode.externalApplication,
                        ),
                      ),
                    ));
                  },
                )),
        ]);
      },
    );
  }

  Widget _buildAppBar(Map<String, dynamic> caseData) {
    return Container(
      padding: EdgeInsets.only(
        top: MediaQuery.of(context).padding.top + 8,
        left: 4,
        right: 8,
        bottom: 10,
      ),
      decoration: const BoxDecoration(
        color: AppTheme.surfaceCard,
        boxShadow: [BoxShadow(color: Colors.black38, blurRadius: 10)],
      ),
      child: Row(
        children: [
          IconButton(
            icon: const Icon(Icons.arrow_back_ios,
                color: AppTheme.textWhite, size: 20),
            onPressed: () => Navigator.pop(context),
          ),
          Expanded(
            child: Text(
              caseData['crime_number'] ?? 'Case Details',
              style: const TextStyle(
                color: AppTheme.textWhite,
                fontWeight: FontWeight.bold,
                fontSize: 16,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          IconButton(
            icon: const Icon(Icons.menu_book, color: AppTheme.tealAccent),
            tooltip: 'Export Case Diary (PRB Form 43, .docx)',
            onPressed: () => launchUrl(ApiService.exportDiaryUri(caseId),
                mode: LaunchMode.externalApplication),
          ),
          IconButton(
            icon: const Icon(Icons.description, color: AppTheme.goldAccent),
            tooltip: 'Memo of Evidence (needs DSR No.)',
            onPressed: _askDsrAndOpenMoE,
          ),
          IconButton(
            icon:
                const Icon(Icons.document_scanner, color: AppTheme.tealAccent),
            tooltip: 'Scan evidence or case documents (AI)',
            onPressed: _scanToDiary,
          ),
          _generatingChargesheet
              ? const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 12),
                  child: SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: AppTheme.goldAccent),
                  ),
                )
              : IconButton(
                  icon: const Icon(Icons.summarize_outlined,
                      color: AppTheme.goldAccent),
                  tooltip: 'Generate AI Chargesheet (.docx) u/s 193 BNSS',
                  onPressed: _generateChargesheet,
                ),
        ],
      ),
    );
  }

  Widget _diaryCard(Map<String, dynamic> d, int index) {
    final artifacts = d['tech_artifacts_obtained'];
    final hasArtifacts = artifacts is Map && artifacts.isNotEmpty;
    final dsrNo = d['dsr_number'];
    final hasMoE = dsrNo != null && dsrNo.toString().isNotEmpty;

    final cardAccents = [
      AppTheme.indigoPrime,
      AppTheme.tealAccent,
      AppTheme.goldAccent,
      const Color(0xFF7C3AED),
      AppTheme.greenVerified,
    ];
    final accent = cardAccents[(index - 1) % cardAccents.length];

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: AppTheme.diaryBg,
        borderRadius: BorderRadius.circular(16),
        border: Border(left: BorderSide(color: accent, width: 4)),
        boxShadow: [
          BoxShadow(
            color: accent.withValues(alpha: 0.15),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: accent.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: accent.withValues(alpha: 0.5)),
                  ),
                  child: Text(
                    'Day $index',
                    style: TextStyle(
                      color: accent,
                      fontWeight: FontWeight.bold,
                      fontSize: 12,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  d['entry_date'] ?? '',
                  style:
                      const TextStyle(color: AppTheme.textSoft, fontSize: 12),
                ),
                const Spacer(),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: AppTheme.greenVerified.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                        color: AppTheme.greenVerified.withValues(alpha: 0.4)),
                  ),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.verified_outlined,
                          size: 10, color: AppTheme.greenVerified),
                      SizedBox(width: 4),
                      Text(
                        'RECORDED',
                        style: TextStyle(
                          color: AppTheme.greenVerified,
                          fontSize: 9,
                          fontWeight: FontWeight.bold,
                          letterSpacing: 0.5,
                        ),
                      ),
                    ],
                  ),
                ),
                if (hasMoE) ...[
                  const SizedBox(width: 6),
                  Tooltip(
                    message: 'Memo of Evidence — DSR No: $dsrNo',
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        gradient: AppTheme.goldGradient,
                        borderRadius: BorderRadius.circular(6),
                        boxShadow: [
                          BoxShadow(
                            color: AppTheme.goldAccent.withValues(alpha: 0.4),
                            blurRadius: 8,
                          ),
                        ],
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.description,
                              size: 10, color: AppTheme.navyDeep),
                          SizedBox(width: 4),
                          Text(
                            'MoE',
                            style: TextStyle(
                              color: AppTheme.navyDeep,
                              fontSize: 9,
                              fontWeight: FontWeight.w900,
                              letterSpacing: 0.5,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ],
            ),
            const SizedBox(height: 12),
            const Text(
              'INVESTIGATION SUMMARY',
              style: TextStyle(
                color: AppTheme.tealAccent,
                fontSize: 10,
                fontWeight: FontWeight.bold,
                letterSpacing: 1,
              ),
            ),
            const SizedBox(height: 6),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: const Color(0xFF0D1535),
                borderRadius: BorderRadius.circular(8),
                border:
                    Border.all(color: AppTheme.indigoPrime.withValues(alpha: 0.3)),
              ),
              child: Text(
                d['investigation_summary'] ?? '',
                style: const TextStyle(
                  color: AppTheme.textWhite,
                  fontSize: 13,
                  height: 1.6,
                ),
              ),
            ),
            const SizedBox(height: 10),
            const Text(
              'ACTION TAKEN',
              style: TextStyle(
                color: AppTheme.goldAccent,
                fontSize: 10,
                fontWeight: FontWeight.bold,
                letterSpacing: 1,
              ),
            ),
            const SizedBox(height: 6),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: const Color(0xFF0E1830),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppTheme.goldAccent.withValues(alpha: 0.2)),
              ),
              child: Text(
                d['action_taken'] ?? '',
                style: const TextStyle(
                  color: AppTheme.textWhite,
                  fontSize: 13,
                  fontStyle: FontStyle.italic,
                  height: 1.6,
                ),
              ),
            ),
            if (hasArtifacts) ...[
              const SizedBox(height: 10),
              const Text(
                'RECORDED CASE DETAILS',
                style: TextStyle(
                  color: AppTheme.crimsonBadge,
                  fontSize: 10,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1,
                ),
              ),
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppTheme.crimsonBadge.withValues(alpha: 0.07),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                      color: AppTheme.crimsonBadge.withValues(alpha: 0.25)),
                ),
                child: Text(
                  _artifactSummary(artifacts),
                  style: const TextStyle(
                    color: AppTheme.textWhite,
                    fontSize: 11,
                    fontFamily: 'monospace',
                    height: 1.5,
                  ),
                ),
              ),
            ],
            if (hasMoE) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  const Icon(Icons.numbers,
                      color: AppTheme.goldAccent, size: 12),
                  const SizedBox(width: 4),
                  Text(
                    'DSR No: $dsrNo',
                    style: const TextStyle(
                      color: AppTheme.goldAccent,
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 10),
            const Divider(color: Color(0xFF1E2B5E), height: 1),
            const SizedBox(height: 8),
            GestureDetector(
              onLongPress: () {
                Clipboard.setData(ClipboardData(text: d['entry_hash'] ?? ''));
                _snack('Hash copied to clipboard.');
              },
              child: Row(
                children: [
                  const Icon(Icons.shield_outlined,
                      size: 10, color: AppTheme.textSoft),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      'SHA-256: ${d['entry_hash'] ?? 'N/A'}',
                      style: const TextStyle(
                        color: AppTheme.textSoft,
                        fontSize: 9,
                        fontFamily: 'monospace',
                        letterSpacing: 0.5,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _infoRow(IconData icon, String label, dynamic value,
      {Color? valueColor}) {
    if (value == null || value.toString().isEmpty) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 13, color: AppTheme.textSoft),
          const SizedBox(width: 6),
          Text(
            '$label: ',
            style: const TextStyle(color: AppTheme.textSoft, fontSize: 12),
          ),
          Expanded(
            child: Text(
              value.toString(),
              style: TextStyle(
                color: valueColor ?? AppTheme.textWhite,
                fontSize: 12,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _artifactSummary(Map<dynamic, dynamic> artifacts) {
    final lines = <String>[];
    artifacts.forEach((k, v) {
      if (v != null) {
        final val = v is List ? v.join(', ') : v.toString();
        if (val.isNotEmpty) lines.add('$k: $val');
      }
    });
    return lines.join('\n');
  }
}
