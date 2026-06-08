class UpdateMetadata {
  final String latestVersion;
  final int buildNumber;
  final String minRequiredVersion;
  final bool forceUpdate;
  final String downloadUrl;
  final List<String> releaseNotes;
  final DateTime? releaseTimestamp;

  UpdateMetadata({
    required this.latestVersion,
    required this.buildNumber,
    required this.minRequiredVersion,
    required this.forceUpdate,
    required this.downloadUrl,
    required this.releaseNotes,
    this.releaseTimestamp,
  });

  factory UpdateMetadata.fromJson(Map<String, dynamic> json) {
    final lv = json['latest_version']?.toString().trim();
    final mrv = json['min_required_version']?.toString().trim();
    final url = json['download_url']?.toString().trim();

    return UpdateMetadata(
      latestVersion: (lv == null || lv.isEmpty || lv == 'null') ? '1.0.0' : lv,
      buildNumber: json['build_number'] != null 
          ? int.tryParse(json['build_number'].toString()) ?? 1 
          : 1,
      minRequiredVersion: (mrv == null || mrv.isEmpty || mrv == 'null') ? '1.0.0' : mrv,
      forceUpdate: json['force_update'] == true || json['force_update']?.toString().toLowerCase() == 'true',
      downloadUrl: url ?? '',
      releaseNotes: (json['release_notes'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
      releaseTimestamp: json['release_timestamp'] != null
          ? DateTime.tryParse(json['release_timestamp'].toString())
          : null,
    );
  }
  
  Map<String, dynamic> toJson() {
    return {
      'latest_version': latestVersion,
      'build_number': buildNumber,
      'min_required_version': minRequiredVersion,
      'force_update': forceUpdate,
      'download_url': downloadUrl,
      'release_notes': releaseNotes,
      'release_timestamp': releaseTimestamp?.toIso8601String(),
    };
  }
}
