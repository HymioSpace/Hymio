import Foundation

/// Backend APIs never redirect credentials or private media to another origin.
final class NoRedirects: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
  func urlSession(
    _ session: URLSession, task: URLSessionTask,
    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
    completionHandler: @escaping @Sendable (URLRequest?) -> Void
  ) { completionHandler(nil) }
  static let session = URLSession(
    configuration: .ephemeral, delegate: NoRedirects(), delegateQueue: nil)
}
