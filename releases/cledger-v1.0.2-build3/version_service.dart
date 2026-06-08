import 'package:package_info_plus/package_info_plus.dart';
import '../models/update_metadata.dart';
import 'api_client.dart';

enum UpdateRequirement {
  none,
  optional,
  mandatory,
}

class VersionCheckResult {
  final UpdateRequirement requirement;
  final UpdateMetadata? metadata;
  final String currentVersionDisplay;

  VersionCheckResult({
    required this.requirement,
    this.metadata,
    required this.currentVersionDisplay,
  });

  bool get hasUpdate => requirement != UpdateRequirement.none;
}

class VersionService {
  final ApiClient _apiClient;

  VersionService(this._apiClient);

  /// Executes the end-to-end version verification check against backend metadata.
  Future<VersionCheckResult> checkForUpdates() async {
    try {
      // 1. Fetch remote update metadata from the backend
      final metadata = await _apiClient.fetchLatestAppVersion();

      // 2. Read native application installation package info
      final packageInfo = await PackageInfo.fromPlatform();
      final currentVersionString = packageInfo.version;
      final currentBuildNumber = int.tryParse(packageInfo.buildNumber) ?? 1;

      final currentDisplay = 'v$currentVersionString (Build $currentBuildNumber)';

      // 3. Primary Deterministic Evaluation: Integer Build Comparison
      bool isUpdateAvailable = metadata.buildNumber > currentBuildNumber;

      // Secondary Fallback: Semantic string comparison if build numbers match
      if (!isUpdateAvailable && metadata.buildNumber == currentBuildNumber) {
        if (_compareSemanticVersions(metadata.latestVersion, currentVersionString) > 0) {
          isUpdateAvailable = true;
        }
      }

      // 4. Resolve update constraints if newer artifact is available
      if (isUpdateAvailable) {
        bool isMandatory = metadata.forceUpdate;

        // Mandatory check: if current version is lower than minRequiredVersion
        if (!isMandatory &&
            _compareSemanticVersions(currentVersionString, metadata.minRequiredVersion) < 0) {
          isMandatory = true;
        }

        return VersionCheckResult(
          requirement: isMandatory ? UpdateRequirement.mandatory : UpdateRequirement.optional,
          metadata: metadata,
          currentVersionDisplay: currentDisplay,
        );
      }

      // App is up to date
      return VersionCheckResult(
        requirement: UpdateRequirement.none,
        metadata: metadata,
        currentVersionDisplay: currentDisplay,
      );
    } catch (e) {
      // Fail gracefully: Return no requirement if metadata endpoint is unreachable/timeouts occur
      print('--> [VersionService] Update check failed silently: $e');
      return VersionCheckResult(
        requirement: UpdateRequirement.none,
        currentVersionDisplay: 'Unknown',
      );
    }
  }

  /// Evaluates semantic version strings (e.g., '1.2.3' vs '1.2.4').
  /// Returns:
  ///   1 if v1 > v2
  ///  -1 if v1 < v2
  ///   0 if v1 == v2
  int _compareSemanticVersions(String v1, String v2) {
    final parts1 = _parseVersionString(v1);
    final parts2 = _parseVersionString(v2);

    for (int i = 0; i < 3; i++) {
      final val1 = i < parts1.length ? parts1[i] : 0;
      final val2 = i < parts2.length ? parts2[i] : 0;

      if (val1 > val2) return 1;
      if (val1 < val2) return -1;
    }

    return 0; // Completely equal semantic hierarchy
  }

  /// Strips build/pre-release modifiers and returns standard integer parts [major, minor, patch]
  List<int> _parseVersionString(String version) {
    // Strip trailing tags like '+1' or '-beta'
    final cleanVersion = version.split('+')[0].split('-')[0];
    return cleanVersion.split('.').map((part) => int.tryParse(part) ?? 0).toList();
  }
}