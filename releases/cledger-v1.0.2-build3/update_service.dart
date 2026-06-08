import 'package:package_info_plus/package_info_plus.dart';
import '../models/update_metadata.dart';
import 'api_client.dart';

class UpdateCheckResult {
  final bool isUpdateAvailable;
  final bool forceUpdate;
  final UpdateMetadata? metadata;
  final String installedVersion;
  final int installedBuildNumber;

  UpdateCheckResult({
    required this.isUpdateAvailable,
    required this.forceUpdate,
    this.metadata,
    required this.installedVersion,
    required this.installedBuildNumber,
  });
}

class UpdateService {
  final ApiClient _apiClient;

  UpdateService(this._apiClient);

  /// Orchestrates fetching update metadata and comparing local vs remote build numbers.
  Future<UpdateCheckResult> checkForUpdate() async {
    final packageInfo = await PackageInfo.fromPlatform();
    final String installedVersion = packageInfo.version;
    final int installedBuildNumber = int.tryParse(packageInfo.buildNumber) ?? 1;

    try {
      final UpdateMetadata metadata = await _apiClient.fetchLatestAppVersion();
      final bool isUpdateAvailable = metadata.buildNumber > installedBuildNumber;

      return UpdateCheckResult(
        isUpdateAvailable: isUpdateAvailable,
        forceUpdate: isUpdateAvailable && metadata.forceUpdate,
        metadata: metadata,
        installedVersion: installedVersion,
        installedBuildNumber: installedBuildNumber,
      );
    } catch (e) {
      // In case of network errors or unreachable endpoint, default to safe operational state
      return UpdateCheckResult(
        isUpdateAvailable: false,
        forceUpdate: false,
        installedVersion: installedVersion,
        installedBuildNumber: installedBuildNumber,
      );
    }
  }
}