package com.lichen.know.engine;

import com.alibaba.fastjson2.JSON;
import lombok.extern.slf4j.Slf4j;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.yaml.snakeyaml.Yaml;

import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.ThreadLocalRandom;

@Slf4j
public class DownloadPDFs {

    private static final String ARXIV_API_BASE = "http://export.arxiv.org/api/query";
    private static final int MAX_RETRIES = 3;
    private static final int BATCH_SIZE = 50;

    public static Map<String, List<String>> readArxivConfig(String path) throws IOException {
        Yaml yaml = new Yaml();
        try (InputStream inputStream = DownloadPDFs.class.getClassLoader().getResourceAsStream(path)) {
            Map<String, Object> config = yaml.load(inputStream);
            @SuppressWarnings("unchecked")
            Map<String, List<String>> categories = (Map<String, List<String>>) config.get("categories");
            return categories;
        }
    }

    public static String getResponse(String query, Map<String, String> metadata, int maxResults, int start) throws Exception {
        if (query != null) {
            metadata.put("all", URLEncoder.encode(query, "UTF-8"));
        }

        StringBuilder combinedQuery = new StringBuilder();
        for (Map.Entry<String, String> entry : metadata.entrySet()) {
            if (combinedQuery.length() > 0) {
                combinedQuery.append("+AND+");
            }
            combinedQuery.append(entry.getKey()).append(":").append(entry.getValue());
        }

        String urlString = ARXIV_API_BASE + "?search_query=" + combinedQuery +
                "&start=" + start + "&max_results=" + maxResults +
                "&sortBy=lastUpdatedDate&sortOrder=descending";

        for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
            try {
                URL url = new URL(urlString);
                HttpURLConnection connection = (HttpURLConnection) url.openConnection();
                connection.setRequestMethod("GET");
                connection.setConnectTimeout(30000);
                connection.setReadTimeout(30000);
                connection.setInstanceFollowRedirects(true);
                connection.setRequestProperty("User-Agent", "Mozilla/5.0");

                int responseCode = connection.getResponseCode();
                if (responseCode == HttpURLConnection.HTTP_OK) {
                    BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream(), "UTF-8"));
                    StringBuilder response = new StringBuilder();
                    String line;
                    while ((line = reader.readLine()) != null) {
                        response.append(line);
                    }
                    reader.close();
                    return response.toString();
                } else if (responseCode == HttpURLConnection.HTTP_MOVED_PERM || 
                           responseCode == HttpURLConnection.HTTP_MOVED_TEMP || 
                           responseCode == 307 || responseCode == 308) {
                    String newUrl = connection.getHeaderField("Location");
                    if (newUrl != null) {
                        System.out.println("Redirecting to: " + newUrl);
                        url = new URL(newUrl);
                        connection = (HttpURLConnection) url.openConnection();
                        connection.setRequestMethod("GET");
                        connection.setConnectTimeout(30000);
                        connection.setReadTimeout(30000);
                        connection.setInstanceFollowRedirects(true);
                        connection.setRequestProperty("User-Agent", "Mozilla/5.0");
                        
                        if (connection.getResponseCode() == HttpURLConnection.HTTP_OK) {
                            BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream(), "UTF-8"));
                            StringBuilder response = new StringBuilder();
                            String line;
                            while ((line = reader.readLine()) != null) {
                                response.append(line);
                            }
                            reader.close();
                            return response.toString();
                        }
                    }
                } else {
                    log.error("response code: " + responseCode);
                }
            } catch (Exception e) {
                if (attempt < MAX_RETRIES - 1) {
                    double waitTime = Math.pow(2, attempt) + ThreadLocalRandom.current().nextDouble(0, 1);
                    System.out.println("API request failed. Retrying in " + String.format("%.2f", waitTime) + " seconds...");
                    Thread.sleep((long) (waitTime * 1000));
                } else {
                    System.out.println("Failed to get response after " + MAX_RETRIES + " attempts: " + e.getMessage());
                    throw e;
                }
            }
        }
        throw new Exception("Failed to get response");
    }

    public static List<String> downloadPdfs(String response, String downloadDir, Set<String> existingIds,
                                            int targetCount, int currentCount) throws Exception {
        Path dirPath = Paths.get(downloadDir);
        Files.createDirectories(dirPath);

        List<String> downloadedIds = new ArrayList<>();

        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            DocumentBuilder builder = factory.newDocumentBuilder();
            Document doc = builder.parse(new ByteArrayInputStream(response.getBytes("UTF-8")));

            NodeList entries = doc.getElementsByTagName("entry");

            for (int i = 0; i < entries.getLength(); i++) {
                if (currentCount + downloadedIds.size() >= targetCount) {
                    break;
                }

                try {
                    Element entry = (Element) entries.item(i);

                    String paperId = null;
                    NodeList idNodes = entry.getElementsByTagName("id");
                    if (idNodes.getLength() > 0) {
                        String fullId = idNodes.item(0).getTextContent();
                        paperId = fullId.substring(fullId.lastIndexOf("/abs/") + 5);
                    }

                    if (paperId == null) {
                        System.out.println("Skipping entry with no ID");
                        continue;
                    }

                    if (existingIds.contains(paperId) || downloadedIds.contains(paperId)) {
                        System.out.println("Skipping existing paper: " + paperId);
                        continue;
                    }

                    String title = "";
                    NodeList titleNodes = entry.getElementsByTagName("title");
                    if (titleNodes.getLength() > 0) {
                        title = titleNodes.item(0).getTextContent().trim()
                                .replace("\n", " ").replace(" ", "_");
                    }

                    String pdfUrl = null;
                    NodeList linkNodes = entry.getElementsByTagName("link");
                    for (int j = 0; j < linkNodes.getLength(); j++) {
                        Element link = (Element) linkNodes.item(j);
                        if ("pdf".equals(link.getAttribute("title"))) {
                            pdfUrl = link.getAttribute("href");
                            break;
                        }
                    }

                    if (pdfUrl != null) {
                        String fileName = paperId + ".pdf";
                        Path filePath = dirPath.resolve(fileName);

                        if (Files.exists(filePath)) {
                            System.out.println("PDF already exists for entry: " + title);
                            continue;
                        }

                        System.out.println("Downloading " + pdfUrl + " to " + filePath);

                        boolean downloadSuccess = false;
                        for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
                            try {
                                URL url = new URL(pdfUrl);
                                HttpURLConnection connection = (HttpURLConnection) url.openConnection();
                                connection.setRequestMethod("GET");
                                connection.setConnectTimeout(30000);
                                connection.setReadTimeout(30000);

                                try (InputStream in = connection.getInputStream();
                                     FileOutputStream out = new FileOutputStream(filePath.toFile())) {
                                    byte[] buffer = new byte[8192];
                                    int bytesRead;
                                    while ((bytesRead = in.read(buffer)) != -1) {
                                        out.write(buffer, 0, bytesRead);
                                    }
                                }
                                downloadSuccess = true;
                                downloadedIds.add(paperId);
                                System.out.println("Successfully downloaded " + paperId + " (" +
                                        (downloadedIds.size() + currentCount) + "/" + targetCount + ")");
                                break;
                            } catch (Exception e) {
                                if (attempt < MAX_RETRIES - 1) {
                                    double waitTime = Math.pow(2, attempt) + ThreadLocalRandom.current().nextDouble(0, 1);
                                    System.out.println("Download failed. Retrying in " + String.format("%.2f", waitTime) + " seconds...");
                                    Thread.sleep((long) (waitTime * 1000));
                                } else {
                                    System.out.println("Failed to download PDF for " + paperId + " after " + MAX_RETRIES + " attempts: " + e.getMessage());
                                }
                            }
                        }
                    } else {
                        System.out.println("PDF link not found for entry: " + title);
                    }
                } catch (Exception e) {
                    System.out.println("Error processing entry: " + e.getMessage());
                    continue;
                }
            }
        } catch (Exception e) {
            System.out.println("Error in downloadPdfs: " + e.getMessage());
            throw e;
        }

        return downloadedIds;
    }

    public static boolean extractArxivMetadata(String paperId, String outputFolder) {
        try {
            String url = "http://export.arxiv.org/api/query?id_list=" + paperId;

            String xmlData = null;
            for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
                try {
                    URL apiUrl = new URL(url);
                    HttpURLConnection connection = (HttpURLConnection) apiUrl.openConnection();
                    connection.setRequestMethod("GET");
                    connection.setConnectTimeout(30000);
                    connection.setReadTimeout(30000);

                    BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream(), "UTF-8"));
                    StringBuilder response = new StringBuilder();
                    String line;
                    while ((line = reader.readLine()) != null) {
                        response.append(line);
                    }
                    reader.close();
                    xmlData = response.toString();
                    break;
                } catch (Exception e) {
                    if (attempt < MAX_RETRIES - 1) {
                        double waitTime = Math.pow(2, attempt) + ThreadLocalRandom.current().nextDouble(0, 1);
                        System.out.println("API request failed for metadata. Retrying in " + String.format("%.2f", waitTime) + " seconds...");
                        Thread.sleep((long) (waitTime * 1000));
                    } else {
                        System.out.println("Failed to get metadata after " + MAX_RETRIES + " attempts: " + e.getMessage());
                        return false;
                    }
                }
            }

            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            DocumentBuilder builder = factory.newDocumentBuilder();
            Document doc = builder.parse(new ByteArrayInputStream(xmlData.getBytes("UTF-8")));

            NodeList entryNodes = doc.getElementsByTagName("entry");
            if (entryNodes.getLength() == 0) {
                System.out.println("No entry found for paper ID: " + paperId);
                return false;
            }

            Element entry = (Element) entryNodes.item(0);

            String title = "";
            NodeList titleNodes = entry.getElementsByTagName("title");
            if (titleNodes.getLength() > 0) {
                title = titleNodes.item(0).getTextContent().trim();
            }

            List<String> authors = new ArrayList<>();
            NodeList authorNodes = entry.getElementsByTagName("author");
            for (int i = 0; i < authorNodes.getLength(); i++) {
                Element author = (Element) authorNodes.item(i);
                NodeList nameNodes = author.getElementsByTagName("name");
                if (nameNodes.getLength() > 0) {
                    authors.add(nameNodes.item(0).getTextContent());
                }
            }

            List<String> categories = new ArrayList<>();
            NodeList categoryNodes = entry.getElementsByTagName("category");
            for (int i = 0; i < categoryNodes.getLength(); i++) {
                Element category = (Element) categoryNodes.item(i);
                String term = category.getAttribute("term");
                if (term != null && !term.isEmpty()) {
                    categories.add(term);
                }
            }

            String abstractText = "";
            NodeList summaryNodes = entry.getElementsByTagName("summary");
            if (summaryNodes.getLength() > 0) {
                abstractText = summaryNodes.item(0).getTextContent().trim();
            }

            String updated = "";
            NodeList updatedNodes = entry.getElementsByTagName("updated");
            if (updatedNodes.getLength() > 0) {
                updated = updatedNodes.item(0).getTextContent();
            }

            String published = "";
            NodeList publishedNodes = entry.getElementsByTagName("published");
            if (publishedNodes.getLength() > 0) {
                published = publishedNodes.item(0).getTextContent();
            }

            Map<String, Object> metadata = new LinkedHashMap<>();
            metadata.put("id", paperId);
            metadata.put("title", title);
            metadata.put("authors", authors);
            metadata.put("categories", categories);
            metadata.put("abstract", abstractText);
            metadata.put("updated", updated);
            metadata.put("published", published);

            Path metadataPath = Paths.get(outputFolder);
            Files.createDirectories(metadataPath);

            Path outputFile = metadataPath.resolve(paperId + ".json");
            try (Writer writer = new OutputStreamWriter(Files.newOutputStream(outputFile), "UTF-8")) {
                writer.write(JSON.toJSONString(metadata, com.alibaba.fastjson2.JSONWriter.Feature.PrettyFormat));
            }

            return true;
        } catch (Exception e) {
            System.out.println("Error extracting metadata for " + paperId + ": " + e.getMessage());
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        String outputFolder = "data/raw/pdf/arxiv";
        String configPath = "arxiv_configs.yaml";
        int targetPdfsPerCategory = 375;

        if (args.length >= 1) {
            outputFolder = args[0];
        }
        if (args.length >= 2) {
            configPath = args[1];
        }
        if (args.length >= 3) {
            targetPdfsPerCategory = Integer.parseInt(args[2]);
        }

        Path outputPath = Paths.get(outputFolder);
        Files.createDirectories(outputPath);

        Set<String> existingIds = new HashSet<>();
        Path existingPdfsPath = Paths.get("data/final/pdf/arxiv/corpus");
        if (Files.exists(existingPdfsPath)) {
            try (DirectoryStream<Path> stream = Files.newDirectoryStream(existingPdfsPath, "*.json")) {
                for (Path file : stream) {
                    existingIds.add(file.getFileName().toString().replace(".json", ""));
                }
            }
        }

        Map<String, List<String>> arxivCategories = readArxivConfig(configPath);

        execute(outputFolder, existingIds, targetPdfsPerCategory, arxivCategories);
    }

    public static void execute(String outputFolder, Set<String> existingIds, int targetPdfsPerCategory,
                            Map<String, List<String>> arxivCategories) throws Exception {
        Map<String, List<String>> successfulDownloads = new HashMap<>();

        for (String category : arxivCategories.keySet()) {
            Path pdfDir = Paths.get(outputFolder, "pdf", category);
            Files.createDirectories(pdfDir);

            List<String> existingPdfs = new ArrayList<>();
            if (Files.exists(pdfDir)) {
                try (DirectoryStream<Path> stream = Files.newDirectoryStream(pdfDir, "*.pdf")) {
                    for (Path file : stream) {
                        existingPdfs.add(file.getFileName().toString().replace(".pdf", ""));
                    }
                }
            }
            successfulDownloads.put(category, existingPdfs);
        }

        for (Map.Entry<String, List<String>> categoryEntry : arxivCategories.entrySet()) {
            String category = categoryEntry.getKey();
            List<String> subCategories = categoryEntry.getValue();

            System.out.println("\n--- Starting downloads for " + category + " ---");

            int pdfsDownloaded = 0;
            int resultsOffset = 0;
            Path pdfDir = Paths.get(outputFolder, "pdf", category);

            while (pdfsDownloaded < targetPdfsPerCategory) {
                System.out.println("Category " + category + ": " + pdfsDownloaded + "/" +
                        targetPdfsPerCategory + " PDFs downloaded. Fetching more...");

                int totalSubCategories = subCategories.size();
                if (totalSubCategories == 0) {
                    System.out.println("No subcategories for " + category + ", skipping");
                    break;
                }

                for (String subCategory : subCategories) {
                    if (pdfsDownloaded >= targetPdfsPerCategory) {
                        break;
                    }

                    Map<String, String> metadata = new HashMap<>();
                    metadata.put("cat", subCategory);
                    metadata.put("submittedDate", "[202401010600+TO+202501010600]");

                    try {
                        String response = getResponse(null, metadata, BATCH_SIZE, resultsOffset);

                        List<String> newIds = downloadPdfs(response, pdfDir.toString(), existingIds,
                                targetPdfsPerCategory, pdfsDownloaded);

                        pdfsDownloaded += newIds.size();
                        successfulDownloads.get(category).addAll(newIds);
                        existingIds.addAll(newIds);

                    } catch (Exception e) {
                        log.error("Error processing " + category + " " + subCategory + ": " + e.getMessage(), e);
                        continue;
                    }
                }

                resultsOffset += BATCH_SIZE;
                Thread.sleep(1000);

                if (resultsOffset > 1000) {
                    System.out.println("Warning: Reached large offset (" + resultsOffset + ") for " + category +
                            ". Only found " + pdfsDownloaded + "/" + targetPdfsPerCategory + " PDFs.");
                    break;
                }
            }
        }

        System.out.println("\n--- Extracting metadata for all downloaded PDFs ---");
        Path metadataFolder = Paths.get(outputFolder, "metadata");
        Files.createDirectories(metadataFolder);

        int totalMetadataSuccess = 0;
        int totalMetadataFailure = 0;

        for (Map.Entry<String, List<String>> entry : successfulDownloads.entrySet()) {
            String category = entry.getKey();
            List<String> paperIds = entry.getValue();

            System.out.println("\nExtracting metadata for " + paperIds.size() + " papers in " + category + "...");
            int successCount = 0;

            for (String paperId : paperIds) {
                Path metadataFile = metadataFolder.resolve(paperId + ".json");
                if (Files.exists(metadataFile)) {
                    System.out.println("Metadata already exists for " + paperId + ", skipping");
                    successCount++;
                    continue;
                }
                if (extractArxivMetadata(paperId, metadataFolder.toString())) {
                    successCount++;
                } else {
                    totalMetadataFailure++;
                }
            }

            totalMetadataSuccess += successCount;
            System.out.println("Successfully extracted metadata for " + successCount + "/" +
                    paperIds.size() + " papers in " + category);
        }

        System.out.println("\n--- Download Summary ---");
        int totalPapers = 0;
        for (Map.Entry<String, List<String>> entry : successfulDownloads.entrySet()) {
            System.out.println(entry.getKey() + ": " + entry.getValue().size() + " PDFs downloaded");
            totalPapers += entry.getValue().size();
        }

        System.out.println("\nTotal PDFs downloaded: " + totalPapers);
        System.out.println("Metadata extracted successfully: " + totalMetadataSuccess);
        System.out.println("Metadata extraction failures: " + totalMetadataFailure);
    }
}